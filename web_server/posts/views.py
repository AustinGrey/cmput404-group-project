from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.contrib.staticfiles import finders
from django.conf import settings

from .models import Post, VisibleTo, Category
from comments.models import Comment
from users.models import Author
from nodes.models import Node
from friendship.models import Friend
from friendship.views import FOAF_verification
import json


from json import loads
from django.core import serializers
from django.contrib.auth.models import AnonymousUser

import json

from social_distribution.utils.endpoint_utils import Endpoint, PagingHandler, Handler
from social_distribution.utils.basic_auth import validate_remote_server_authentication

import requests
import base64
import re
# used for stripping url protocol
url_regex = re.compile(r"(http(s?))?://")


# No Authentication Required
def retrieve_all_public_posts_on_local_server(request):
    """
    For endpoint http://service/posts
    Retrieves all public posts located on the server
    Methods: GET
    :param request: should specify Accepted content-type
    :returns: application/json | text/html
    """
    def json_handler(request, posts, pager, pagination_uris):
        output = {
            "query": "posts",
            "count": pager.count,
            "size": len(posts),
            "posts": [post.to_api_object() for post in posts]
        }
        (prev_uri, next_uri) = pagination_uris
        if prev_uri:
            output['prev'] = prev_uri
        if next_uri:
            output['next'] = next_uri

        return JsonResponse(output)

    return Endpoint(request, Post.objects.filter(visibility="PUBLIC").order_by('-published'), [
        PagingHandler("GET", "application/json", json_handler)
    ]).resolve()

def check_get_perm(request, api_object_post):
    """
    Checks the permissions on a post api object to see if it can be seen by the currently authenticated user
    """
    visibility = api_object_post["visibility"]

    # Foreign servers can access all posts, unless they are 'SERVERONLY',
    # or if image or post sharing has been turned off
    if request.remote_server_authenticated:
        if visibility != Post.SERVERONLY:
            allowed_post_types = []
            if request.remote_server_authenticated_for_images:
                allowed_post_types += [Post.TYPE_JPEG, Post.TYPE_PNG]
            if request.remote_server_authenticated_for_posts:
                allowed_post_types += [Post.TYPE_BASE64,
                                       Post.TYPE_MARKDOWN, Post.TYPE_PLAIN]
            return api_object_post['contentType'] in allowed_post_types
        else:
            return False

    user_id = url_regex.sub("", request.user.uid).rstrip("/")

    author_id = url_regex.sub("", api_object_post["author"]['id']).rstrip("/")

    if user_id == author_id or visibility == Post.PUBLIC:
        return True

    elif visibility == Post.FOAF:
        # getting the friends of the author
        return FOAF_verification(request, author_id)
    elif visibility == Post.SERVERONLY:
        if request.user.host == Author.objects.get(uid=author_id).host:
            return True
    elif visibility == Post.PRIVATE:
        # The visibleTo list contains protocols, which we dont want
        no_protocol_visible_to = [
            re.sub(r'http(s)*://', '', vt) for vt in api_object_post["visibleTo"]]
        if user_id in no_protocol_visible_to:
            return True
    elif visibility == Post.FRIENDS:
        author_friends = Friend.objects.filter(author_id=author_id)
        for friend in author_friends:
            if user_id == url_regex.sub("", friend.friend_id).rstrip("/"):
                return True
    else:
        return False

@validate_remote_server_authentication()
def retrieve_single_post_with_id(request, post_id):
    """
    For endpoint http://service/posts/{POST_ID}

    Methods
        - Accept:

    GET
        - application/json: returns the post in json format
        - text/html: view the post while logged into our web service. If the post is an image it will return raw
            image data
    POST
        - inserts a post with the specified post_id. Will error if that post already exists
    PUT
        - inserts a post, updates the post if it already exists

    For consistency, it maintains the same pageable format as http://service/posts if JSON is requested
    If HTML is requested it will return a page that will view the post details, or if the post is an image it
    will respond directly with image data for use in hosting images.
    :param request: should specify Accepted content-type
    :returns: application/json | text/html | image/jpg | image/png
    """
    def get_json(request, posts, pager, pagination_uris):
        post_list = [post.to_api_object() for post in posts if check_get_perm(request, post.to_api_object())]
        output = {
            "query": "post",
            "count": len(post_list),
            "size": len(post_list),
            "posts": post_list,
        }
        return JsonResponse(output)

    def get_html_or_image(request, posts, pager, pagination_uris):
        post = Post.objects.get(id=post_id)
        if post.contentType == post.TYPE_PNG or post.contentType == post.TYPE_JPEG:
            if not check_get_perm(request, post.to_api_object()):
                # The user does not have permission to access this post, they must be served the 401 image
                with open(finders.find('401-image.png'), 'rb') as f:
                    return HttpResponse(f.read(), content_type='image/png', status=401)
            # Note, this REQUIRES that the content be in base64 format.
            response = HttpResponse(base64.b64decode(post.content), status=200)
            response['Content-Type'] = post.contentType
            return response

        if not check_get_perm(request, post.to_api_object()):
            return HttpResponse("You do not have permission to see this post", status=401)
        return render(request, 'posts/post.html', {'post': post})

    def insert_or_update_post(request):
        """
        Inserts or updates a post with the given post id. Whether or not we reject the request if the post already
        exists depends on the request method: PUT updates, POST rejects
        """
        # First we find out if the post exists
        try:
            post = Post.objects.get(id=post_id)
        except Post.DoesNotExist as e:
            post = None

        if post is not None and request.method == 'POST':
            return HttpResponse(f"Post ID '{post_id}' already exists, and cannot be updated by POST, try PUT instead.",
                                status=400)

        # Create the post if it does not exist
        if post is None:
            post = Post(id=post_id)

        # Insert all the provided fields

        # There might be a lot of different keys passed, and some keys might not get passed and are entirely optional.
        # Thus we need to carefully consider each key and see if we can set that value for the post

        visible_to_list = None
        post_author = None
        post_comments = None
        vars = json.loads(request.body)
        for key in vars:
            # Ignore passed in values that can't be stored on posts
            if not hasattr(post, key) and key not in ['author']:
                continue

            if key == 'id':
                # We ignore a passed in id, since the id was already specified in the url
                continue
            elif key == 'visibleTo':
                #  visibleTo is a Many to One relationship, we need to create the objects that will be bound to the post
                visible_to_list = [
                    VisibleTo(author_uid=re.sub(r'http(s)?://', '', author_uid))
                    for author_uid in vars.get(key)
                ]
            elif key == 'categories':
                post.categories.clear()
                # Look up the categories or create them if they are new
                for category in vars['categories']:
                    c, created = Category.objects.get_or_create(
                        name=category)
                    post.categories.add(c)
            elif key == 'unlisted':
                if vars.get(key) == 'true':
                    setattr(post, key, True)
                elif vars.get(key) == 'false':
                    setattr(post, key, False)
            elif key == 'comments':
                # We store the comments to add to the post once it is saved to the database
                # @todo merge with Hyeon's code that supports foreign comment authors
                post_comments = vars['comments']
            elif key == 'author':
                # It is unclear whether the spec expects a full user object, or just an author id url
                # We need to prepare for both
                if type(vars['author']) == dict:
                    author_uid = re.sub(r'http(s)?://', '', vars['author']['id'])
                else:
                    author_uid = re.sub(r'http(s)?://', '', vars['author'])

                # Our system does not store foreign data. We must validate that the author is not foreign:
                try:
                    post_author = Author.objects.get(uid=author_uid)
                except Author.DoesNotExist as e:
                    return HttpResponse("We do not support attaching posts to Authors not signed up on the local server"
                                        f". Please send your post to the server the foreign author '{author_uid}' "
                                        "belongs to.",
                                        status=400)

                # You need permission to attach a post to an author. Servers are root, and logged in users can only
                # attach posts to themselves
                if not request.remote_server_authenticated and post_author != request.user:
                    return HttpResponse(f"You do are not authorized to attach a post to an author other than yourself '{request.user.uid}'",
                                        status=400)

                post.author = post_author
            else:
                # All other fields
                setattr(post, key, vars.get(key))
        post.size = 0
        post.save()

        # Set the visibleTo if it was passed, start by removing all the visibleTo that currently exist
        if visible_to_list is not None:
            post.visibleTo.all().delete()
            for vt in visible_to_list:
                vt.accessed_post = post
                vt.save()

        return JsonResponse({"success": "Post updated"})


    # Get a single post
    return Endpoint(request, Post.objects.filter(id=post_id), [
        PagingHandler("GET", "text/html", get_html_or_image),
        PagingHandler("GET", "application/json", get_json),
        Handler("PUT", "*/*", insert_or_update_post),
        Handler("POST", "*/*", insert_or_update_post),

    ]).resolve()


@validate_remote_server_authentication()
def comments_retrieval_and_creation_to_post_id(request, post_id):

    def get_handler(request, comments, pager, pagination_uris):
        if not Post.objects.filter(id=post_id).exists():
            return JsonResponse({
                "success": False,
                "message": "Post Does Not Exists"
            }, status=404)

        comments_list = []
        for comment in comments:
            c = comment.to_api_object()
            if 'error' in c['author']:
                # The comment could not be retrieved, we might have temporarily lost connection
                continue
            content = {
                "author": c["author"],
                "content": c["comment"],
                "contentType": c["contentType"],
                "published": c["published"],
                "id": c["id"]
            }
            comments_list.append(content)

        output = {
            "query": "comments",
            "count": pager.count,
            "size":  min(int(request.GET.get('size', 10)), 50),
            "comments": comments_list
        }

        (prev_uri, next_uri) = pagination_uris
        if prev_uri:
            output['prev'] = prev_uri
        if next_uri:
            output['next'] = next_uri

        return JsonResponse(output)

    def post_handler(request):
        # JSON post body of what you post to a posts' comemnts
        # POST to http://service/posts/{POST_ID}/comments
        output = {
            "query": "addComment",
        }

        # checks if local host
        if Post.objects.filter(id=post_id).exists():
            # checks visibility of the post
            if not check_get_perm(request, Post.objects.get(id=post_id).to_api_object()):
                return JsonResponse(
                    {
                        "query": "addComment",
                        "success": False,
                        "message": "Comment not allowed"
                    }, status=403
                )

        # change body = request.POST to body = request.body.decode('utf-8'),
        # because request.POST only accepts form, but here is json format.
        # change new_comment.comment to new_comment.content,
        # because that's how it defined in comment model.
        try:
            body = request.body.decode('utf-8')
            comment_info = loads(body)
            comment_info = comment_info['comment']
            new_comment = Comment()
            new_comment.contentType = comment_info['contentType']
            new_comment.content = comment_info['comment']
            new_comment.published = comment_info['published']
            new_comment.author = url_regex.sub(
                '', comment_info['author']['id']).rstrip("/")
            new_comment.parentPost = Post.objects.filter(id=post_id).first()
            new_comment.save()
            output['success'] = True
            output['message'] = "Comment added"
        except Exception as e:
            output['success'] = False
            output['message'] = "Comment not allowed"
            output['error'] = str(e)
        finally:
            if output["success"]:
                return JsonResponse(output, status=200)
            else:
                return JsonResponse(output, status=403)

    def FOAF_verification_post(auth_user, author):
        auth_user = url_regex.sub("", auth_user).rstrip("/")
        author = url_regex.sub("", author).rstrip("/")

        auth_user_node = auth_user.split("/author")[0]

        try:
            node_object = Node.objects.get(foreign_server_hostname=auth_user_node)
        except Node.DoesNotExist as e:
            print(f"Attempt to FOAF verify friend node hostname '{auth_user_node}' but it does not exists so checking the api loation")
            try:
                node_object = Node.objects.get(foreign_server_api_location=auth_user_node)
            except Node.DoesNotExist as e:
                print(f"Attempt to FOAF verify friend node hostname '{auth_user_node}' but we do not have access to that node.")
                return False

        username = node_object.username_registered_on_foreign_server
        password = node_object.password_registered_on_foreign_server
        api = node_object.foreign_server_api_location

        api = "http://{}/author/{}/friends".format(
            api, "{}/author/{}".format(api, auth_user))
        if node_object.append_slash:
            api = api + "/"
        response = requests.get(api, auth=(username, password))

        if response.status_code != 200:
            api = node_object.foreign_server_api_location
            api = "http://{}/author/{}/friends".format(
                api, auth_user.split("author/")[-1])
            if node_object.append_slash:
                api = api + "/"
            response = requests.get(api, auth=(username, password))

        if response.status_code == 200:
            try:
                friends_list = response.json()
            except Exception as e:
                print(f"Attempt to decode FOAF verification response from '{auth_user_node}' failed")
                return False
            for user in friends_list["authors"]:
                if url_regex.sub("", user).rstrip("/") == url_regex.sub("", author).rstrip("/"):
                        return True

        return False


    def check_perm_foreign_user(user_id, api_object_post):
        """
        Checks the permissions on a post api object to see if it can be seen by the currently authenticated user
        """

        visibility = api_object_post["visibility"]

        if visibility == Post.SERVERONLY:
            return False

        author_id = url_regex.sub(
            "", api_object_post["author"]['id']).rstrip("/")
        user_id = url_regex.sub("", user_id).rstrip("/")

        if visibility == Post.PUBLIC:
            return True

        elif visibility == Post.FOAF:
            # getting the friends of the author
            return FOAF_verification_post(user_id, author_id)

        elif visibility == Post.PRIVATE:
            for user in api_object_post["visibleTo"]:
                if user_id == url_regex.sub("", user).rstrip("/"):
                    return True
        elif visibility == Post.FRIENDS:
            if Friend.objects.filter(author_id=author_id).filter(friend_id=user_id).exists():
                return True
        else:
            return False

    def foreign_post_handler(request):
        # JSON post body of what you post to a posts' comemnts
        # POST to http://service/posts/{POST_ID}/comments
        output = {
            "query": "addComment",
        }

        body = request.body.decode('utf-8')
        comment_info = loads(body)
        comment_info = comment_info['comment']

        # checks if local host
        if Post.objects.filter(id=post_id).exists():
            # checks visibility of the post
            if not check_perm_foreign_user(url_regex.sub('', comment_info['author']['id']).rstrip("/"), Post.objects.get(id=post_id).to_api_object()):
                return JsonResponse(
                    {
                        "query": "addComment",
                        "success": False,
                        "message": "Comment not allowed"
                    }, status=403
                )
        try:
            new_comment = Comment()
            new_comment.contentType = comment_info['contentType']
            new_comment.content = comment_info['comment']
            new_comment.published = comment_info['published']
            new_comment.author = url_regex.sub(
                '', comment_info['author']['id']).rstrip("/")
            new_comment.parentPost = Post.objects.filter(id=post_id).first()
            new_comment.save()
            output['success'] = True
            output['message'] = "Comment added"
        except Exception as e:
            output['success'] = False
            output['message'] = "Comment not allowed"
            output['error'] = str(e)
        finally:
            if output["success"]:
                return JsonResponse(output, status=200)
            else:
                return JsonResponse(output, status=403)

    def api_response(request, comments, pager, pagination_uris):
        size = min(int(request.GET.get('size', 10)), 50)
        output = {
            "query": "comments",
            "count": pager.count,
            "size": size,
            "comments": [comment.to_api_object() for comment in comments]
        }

        (prev_uri, next_uri) = pagination_uris
        if prev_uri:
            output['prev'] = prev_uri
        if next_uri:
            output['next'] = next_uri
        return JsonResponse(output)

    if request.user.is_authenticated:
        return Endpoint(request, Comment.objects.filter(parentPost=post_id).order_by("-published"),
                        [Handler("POST", "application/json", post_handler),
                         PagingHandler("GET", "application/json", get_handler)]
                        ).resolve()
    else:
        auth = request.META['HTTP_AUTHORIZATION'].split()
        if len(auth) == 2:
            if auth[0].lower() == "basic":
                uname, passwd = base64.b64decode(
                    auth[1]).decode('utf-8').rsplit(':', 1)
        node = Node.objects.get(foreign_server_username=uname)
        image_type = ["image/png;base64", "image/jpeg;base64"]
        post_type = ["text/plain", "text/markdown"]
        if Post.objects.filter(id=post_id).exists():
            type = Post.objects.get(id=post_id).contentType

            if type in post_type and not node.post_share:
                return JsonResponse(
                    {
                        "success": False,
                        "message": "Post or image sharing is turned off"
                    }, status=403
                )
            if type in image_type and not node.image_share:
                return JsonResponse(
                    {
                        "success": False,
                        "message": "Post or image sharing is turned off"
                    }, status=403
                )

        return Endpoint(request, Comment.objects.filter(parentPost=post_id).order_by("-published"),
                        [Handler("POST", "application/json", foreign_post_handler, False),
                         PagingHandler("GET", "application/json", api_response)]
                        ).resolve()


@login_required  # Local server usage only
def fetch_public_posts_from_nodes(request):
    """
    Fetches public posts from all the nodes available to the server

    Due to the nature of this API, getting deep pages may take a really long time as random access is not possible

    :param request:
    :return:
    """
    output = {
        'query': "getPosts",
        'page': 0,
        'size': 10,
        'count': 0,
        'posts': [],
        'errors': dict()
    }

    # First we need to find out what page of results they are looking for, and how many
    try:
        output['page'] = int(request.GET.get('page', '0'))
        output['size'] = int(request.GET.get('size', '10'))
    except Exception as e:
        output['errors'] = str(e)
        # Bad request with invalid parameters
        return JsonResponse(output, status=400)

    # Then we need to track the pages of each Node, pull their results and merge them together
    class NodePager:
        def __init__(self, api_location, username, password, page, size):
            self.api_location = api_location
            self.username = username
            self.password = password
            self.page = page
            self.size = size
            self.results = None

        def fetch_page(self):
            """
            Gets the current page of public posts from the node. Returns empty list if no results or error.
            Caches the results so it will only fetch the page if the page has not already been fetched
            """
            if self.results is not None:
                return self.results

            try:
                req_params = {
                    'size' : self.size
                }
                if self.page > 0:
                    req_params['page'] = self.page

                response = requests.get(self.api_location,
                                        auth=(self.username, self.password),
                                        headers={
                                            'Accept': 'application/json'
                                        },
                                        params=req_params)
            except Exception as e:
                print(f"Error connecting to node '{self.api_location}': {e}")
                return []
            if response.status_code != 200:
                print(f"Response was {response.status_code} when fetching public posts from {self.api_location}")
                self.results = []
            else:
                try:
                    res_json = response.json()
                    self.results = res_json['posts']
                except:
                    self.results = []
            return self.results

        def next_page(self):
            self.page += 1
            self.results = None

    class NodeCollectionPager:
        """
        Manages a collection of node pagers, returning pages of their combined results
        """

        def __init__(self, size):
            self.size = size
            self.node_pagers = dict()
            for node in Node.objects.all():
                # Create a pager so we can handle paging through all the results
                self.node_pagers[node.foreign_server_hostname] = NodePager(node.get_safe_api_url('posts'),
                                                                           node.username_registered_on_foreign_server,
                                                                           node.password_registered_on_foreign_server,
                                                                           0,  # Always start on the first page, we have no other way to ensure all results are seen
                                                                           size)

        def get_page(self, page):
            """
            Gets the specified page by individually and sequentially querying each node and combining results until the
            desired page is reached. Thus getting deep pages should be avoided if possible.
            """
            current_page = 0
            current_results_queue = []
            while len(self.node_pagers) > 0 and len(current_results_queue) < ((page+1) * self.size):
                # make an array from the keys so that we can delete keys during the loop
                for node in [*self.node_pagers.keys()]:
                    pager = self.node_pagers[node]
                    pager_page = pager.fetch_page()
                    if len(pager_page) == 0:
                        # This node has exhausted it's pages
                        del self.node_pagers[node]
                    current_results_queue += pager_page
                    pager.next_page()

            return current_results_queue[page*self.size:(page+1)*self.size]

    manager = NodeCollectionPager(10)
    output['posts'] = manager.get_page(output['page'])

    # Quick adaptor for groups not following the spec
    for post in output['posts']:
        if 'content_type' in post and 'contentType' not in post:
            post['contentType'] = post['content_type']

    return JsonResponse(output)


    # for node in Node.objects.all():
    #     # Get the url of the api
    #     api_url = node.get_safe_api_url('posts')
    #
    #     response = requests.get(api_url,
    #                             auth=(node.username_registered_on_foreign_server,
    #                                   node.password_registered_on_foreign_server),
    #                             headers={'Accept': 'application/json'})
    #     if response.status_code != 200:
    #         output['errors'][node.foreign_server_hostname] = f"Received response code {response.status_code} " \
    #                                                          f"at api endpoint: {api_url}"
    #         continue
    #
    #     try:
    #         json = response.json()
    #     except Exception as e:
    #         output['errors'][node.foreign_server_hostname] = f"During JSON decode got {e} for response like " \
    #                                                          f"'{response.content[:20]}...'"
    #         continue
    #
    #     for post in json['posts']:
    #         output['count'] += 1
    #         output['posts'].append(post)
    #         if output['count'] >= output['size']:
    #             break
    #
    #     if output['count'] >= output['size']:
    #         break

    return JsonResponse(output, status=200)


@login_required
def proxy_foreign_server_image(request, image_url):
    """
    For markdown posts that contain images in them, we need to proxy the request through our server.
    This is because foreign servers require authorization. Requires an image url, which should NOT include the protocol

    If the url passed is not for a specific node we have connections for, it will be returned with the https protocol
    appended so that other img urls are not affected and resolve as normal.
    """
    image_url_parts = image_url.split('/')
    credentials = None
    try:
        node = Node.objects.get(foreign_server_hostname=image_url_parts[0])
        credentials = (node.username_registered_on_foreign_server,
                       node.password_registered_on_foreign_server)
    except Node.DoesNotExist as e:
        # This url is not for a node that we have credentials for, we have to return some sort of message that
        # Will inform the front end to NOT replace the url. This is done just by stating an error status.
        return HttpResponse("We do not have a connection to this node", status=404)

    request_args = {
        'headers': {
            'Accept': 'application/json'
        }
    }
    if credentials is not None:
        request_args['auth'] = credentials
    # Make a request to the url, and pass in the credentials if they exist
    response = requests.get('http://' + image_url, **request_args)
    if response.status_code != 200:
        # Return the original server response as an HTTP response
        return HttpResponse(f'The server failed to deliver a valid response. The response was {response.content}', status=response.status_code)

    try:
        # Decode the json response to get the post
        post = response.json()['posts'][0]
    except Exception as e:
        return HttpResponse(f'The foreign server responded, but the post returned was invalid: {e}', status=500)

    # Otherwise read the image data and return the image
    uri = ("data:" + post['contentType'] + ", " + post['content'])

    return HttpResponse(uri, content_type=response.headers['Content-Type'])
