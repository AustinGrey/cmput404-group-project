from social_distribution.utils.endpoint_utils import Endpoint, Handler, PagingHandler
import pytz
from django.shortcuts import render, get_object_or_404, redirect, render_to_response
from django.http import HttpResponse, JsonResponse
from django.core.paginator import Paginator
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, JsonResponse, QueryDict, Http404
from users.models import Author
from nodes.models import Node
from friendship.models import Friend
from posts.models import Post, Category
from comments.models import Comment
from django.db.models import Q
from django.utils import timezone
from django.urls import reverse
from django.template import RequestContext
from urllib.parse import urlparse, urlunparse
from uuid import UUID
from social_distribution.utils.basic_auth import validate_remote_server_authentication
from friendship.views import FOAF_verification

import math
from django.conf import settings

import requests

from django.contrib.auth.decorators import login_required


import json
import datetime
import re
import base64


# used for stripping url protocol
url_regex = re.compile(r"(http(s?))?://")


DEFAULT_PAGE_SIZE = 10


def retrieve_friends_of_author(authorid):
    response_data = []
    if Friend.objects.filter(author_id=authorid).exists():
        # get friend id from Friend table
        friends = Friend.objects.filter(author_id=authorid)
        # compose response data
        for each in friends:
            entry = {}
            if Author.objects.filter(uid=each.friend_id).exists():

                friend = Author.objects.get(pk=each.friend_id)
                entry['id'] = friend.uid
                entry['host'] = friend.host
                entry['displayName'] = friend.display_name
                entry['url'] = friend.url
                entry['firstName'] = friend.first_name
                entry['lastName'] = friend.last_name
                response_data.append(entry)
            # foreign friend
            else:

                foreign_server_hostname = each.friend_id.split("/")[0]
                if Node.objects.filter(foreign_server_hostname=foreign_server_hostname).exists():
                    node = Node.objects.get(pk=foreign_server_hostname)
                    url = "http://{}/{}".format(
                        node.foreign_server_api_location.rstrip("/"), each.friend_id.split("/")[1])

                    res = requests.get(url)

                    if res.status_code == 200 or res.status_code == 201:
                        foreign_friend = res.json()
                        entry['id'] = foreign_friend['id']
                        entry['host'] = foreign_friend['host']
                        entry['displayName'] = foreign_friend['displayName']
                        entry['url'] = foreign_friend['url']
                        response_data.append(entry)

    return response_data

# http://service/author endpoint
# Author : Ida Hou


def return_all_authors_registered_on_local_server(request):
    if request.method != 'GET':
        return HttpResponse("Method Not Allowed", status=405)
    authors = Author.objects.filter(is_active=1).filter(is_superuser=0)
    data = []
    for author in authors:
        each = {}
        each['id'] = "https://" + author.uid
        each['host'] = "https://" + author.host
        each['url'] = "https://" + author.url
        each['displayName'] = author.display_name
        each['firstName'] = author.first_name
        each['lastName'] = author.last_name
        # each['friends'] = retrieve_friends_of_author(author.uid) # uncomment if should return friend list
        data.append(each)

    return JsonResponse(data, safe=False)


# Ida Hou
# return a list of author id that are currently stored in database and
# are not friend with current author
# internal endpoint -  not used
@login_required
def view_list_of_available_authors_to_befriend(request, author_id):
    if request.method != 'GET':
        return HttpResponse("Method Not Allowed", status=405)
    host = request.get_host()
    author_id = host + "/author/" + str(author_id)
    if not Author.objects.filter(is_active=1).filter(uid=author_id).exists():
        return HttpResponse("No Author Record", status=404)
    authors_on_record = Author.objects.filter(~Q(uid=author_id)).filter(
        is_active=1).filter(is_superuser=0)
    response_data = {}
    response_data["available_authors_to_befriend"] = []
    response_data["errors"] = {}
    for each in authors_on_record:
        entry = {}
        entry["id"] = each.uid
        entry["displayName"] = each.display_name
        entry["host"] = each.host
        entry["url"] = each.url
        response_data["available_authors_to_befriend"].append(entry)
    # query foreign users
    nodes = Node.objects.all()
    for node in nodes:
        url = "http://{}/author".format(node.foreign_server_api_location)
        res = requests.get(url, auth=(
            node.username_registered_on_foreign_server, node.password_registered_on_foreign_server))
        if res.status_code == 200 or res.status_code == 201:
            # We cannot trust that the server will return a valid json list. Sanitize
            try:
                res_json = res.json()
                response_data["available_authors_to_befriend"] = response_data["available_authors_to_befriend"] + res.json()
            except Exception as e:
                response_data['errors'][node.get_safe_api_url()] = f"Could not parse json response, exception: {e}"
    # if author has no friends
    if not Friend.objects.filter(author_id=author_id).exists():
        return JsonResponse(response_data)

    existing_friends = Friend.objects.filter(author_id=author_id)
    existing_friends_set = set([each.friend_id for each in existing_friends])
    available_authors_to_friend = []
    for each in response_data["available_authors_to_befriend"]:
        if not url_regex.sub('', each['id']) in existing_friends_set:
            available_authors_to_friend.append(each)
    response_data["available_authors_to_befriend"] = available_authors_to_friend

    return JsonResponse(response_data)


# Ida Hou
# service/author/unfriend endpoint handler
# post request body
# {
#  author_id :http://127.0.0.1:8000/author/019fcd68-9224-4d1d-8dd3-e6e865451a31
#  friend_id : http://127.0.0.1:8000/author/019fcd68-9224-4d1d-8dd3-e6e865451a31
#
# }
# internal endpoints


# @login_required
def unfriend(request):
    if request.method == 'POST':
        body = request.body.decode('utf-8')
        body = json.loads(body)
        # strip protocol from url
        author_id = url_regex.sub('', body.get("author_id", ""))
        friend_id = url_regex.sub('', body.get("friend_id", ""))
        if not author_id or not friend_id:
            # Unprocessable Entity
            return HttpResponse("post request body missing fields", status=422)

        if Friend.objects.filter(author_id=author_id).filter(friend_id=friend_id).exists():
            Friend.objects.filter(author_id=author_id).filter(
                friend_id=friend_id).delete()
        else:
            return HttpResponse("Friendship does not exist!", status=404)
        if Friend.objects.filter(author_id=friend_id).filter(friend_id=author_id).exists():
            Friend.objects.filter(author_id=friend_id).filter(
                friend_id=author_id).delete()
        return HttpResponse("Unfriended !", status=200)

    return HttpResponse("Method Not Allowed", status=405)
# handler for endpoint: http://service/author/<str:author_id>/update
# post body data requirement
# require a json objects with following fields:
# first_name, last_name, email, bio, github, display_name, delete
# allow authors delete themselves (delete  = True if to be deleted)
# if no changes to above field, original values should be passed
# username, uid, id, url, host of author can't be changed


def check_missing_post_body_field_and_return_422(body, fields_to_check):
    for each in fields_to_check:
        if body.get(each, None) is None:
            return HttpResponse("Post body missing fields: {}".format(each), status=422)
    return None

# internal endpoint - not used


@login_required
def update_author_profile(request, author_id):
    if request.method != 'POST':
        return HttpResponse("Method Not Allowed", status=405)
    # compose full url of author
    host = request.get_host()
    author_id = host + "/author/" + str(author_id)
    if not Author.objects.filter(uid=author_id).exists():
        return HttpResponse("Author Does not Exist", status=404)
    # unpack post body data
    body = request.body.decode('utf-8')
    body = json.loads(body)
    delete = body.get('delete', None)
    response = check_missing_post_body_field_and_return_422(
        body, ['delete', 'first_name', 'last_name', 'email', 'bio', 'github', 'display_name'])
    # check entries in post request body
    if response:
        return response
    if delete:

        author_to_be_deleted = Author.objects.get(
            pk=author_id)
        author_to_be_deleted.delete()
    else:
        obj, created = Author.objects.update_or_create(
            uid=author_id,
            defaults={'first_name': body.get('first_name'), 'last_name': body.get(
                'last_name'),
                'email': body.get('email'), 'bio': body.get('bio'), 'github': body.get('github'),
                'display_name': body.get('display_name')},
        )

    return HttpResponse("Author successfully updated", status=200)


# Ida Hou
# service/author/{author_id} endpoint handler
def retrieve_author_profile(request, author_id):
    if request.method == 'GET':
        # compose full url of author
        host = request.get_host()
        author_id = host + "/author/" + str(author_id)

        # only active authors are retrivable
        author = get_object_or_404(
            Author.objects.filter(is_active=1), uid=author_id)
        response_data = {}
        response_data['id'] = author.uid
        response_data['host'] = author.host
        response_data['url'] = author.url
        response_data['displayName'] = author.display_name
        response_data['friends'] = retrieve_friends_of_author(author.uid)
        # add optional information of current user
        response_data['github'] = author.github
        response_data['firstName'] = author.first_name
        response_data['lastName'] = author.last_name
        response_data['email'] = author.email
        response_data['bio'] = author.bio
        return JsonResponse(response_data)

    return HttpResponse("You can only GET the URL", status=405)

@validate_remote_server_authentication()
def post_creation_and_retrieval_to_curr_auth_user(request):
    """
    Endpoint handler for service/author/posts
    POST is for creating a new post using the currently authenticated user
    GET is for retrieving posts visible to currently authenticated user

    For servers, the 'currently authenticated user' is a node, and if you are authenticated as a node, you are root.
    Thus we return all the posts, unless they are 'SERVERONLY'
    :param request:
    :return:
    """
    def create_new_post(request):
        # POST to http://service/author/posts
        # Create a post to the currently authenticated user

        # First get the information out of the request body
        size = len(request.body)

        #body = json.load(body)
        # body = dict(x.split("=") for x in body.split("&"))

        #post = body['post']
        post = request.POST

        new_post = Post()

        # Post ID's are created automatically in the database
        # new_post.id = post['id']                  #: "de305d54-75b4-431b-adb2-eb6b9e546013",

        #: "A post title about a post about web dev",
        new_post.title = post['title']

        # Source and origin are the same, and depend on the ID so we wait until after the post gets saved to
        # generate this URLS
        # new_post.source    = post['source']       #: "http://lastplaceigotthisfrom.com/posts/yyyyy"
        # new_post.origin    = post['origin']       #: "http://whereitcamefrom.com/posts/zzzzz"

        # : "This post discusses stuff -- brief",
        new_post.description = post['description']

        # If the post is an image, the content would have been provided as a file along with the upload
        if len(request.FILES) > 0:
            file_type = request.FILES['file'].content_type
            allowed_file_type_map = {
                'image/png': Post.TYPE_PNG,
                'image/jpg': Post.TYPE_JPEG
            }

            if file_type not in allowed_file_type_map.keys():
                return JsonResponse({
                    'success': 'false',
                    'msg': f'You uploaded an image with content type: {file_type}, but only one of {allowed_file_type_map.keys()} is allowed'
                })

            # : "text/plain"
            new_post.contentType = allowed_file_type_map[file_type]
            new_post.content = base64.b64encode(
                request.FILES['file'].read()).decode('utf-8')
        else:
            new_post.contentType = post['contentType']  # : "text/plain",
            new_post.content = post['content']      #: "stuffs",

        new_post.author = request.user         # the authenticated user

        # Categories added after new post is saved

        new_post.count = 0                  #: 1023, initially the number of comments is zero
        new_post.size = size                 #: 50, the actual size of the post in bytes

        # This is not a property that gets stored, but rather a link to the comments of this post that should
        # be generated on the fly.
        # new_post.next        = post['next']         #: "http://service/posts/{post_id}/comments",

        # We do not permit adding comments at the same time a post is created, so this field is not created
        # new_post.comments = post['comments']  #: LIST OF COMMENT,

        current_tz = pytz.timezone('America/Edmonton')
        timezone.activate(current_tz)
        #: "2015-03-09T13:07:04+00:00",
        new_post.published = str(datetime.datetime.now())
        new_post.visibility = post['visibility'].upper()   #: "PUBLIC",

        #: true
        new_post.unlisted = True if 'unlisted' in post and post['unlisted'] == 'true' else False

        new_post.save()

        # Now we can set source and origin
        new_post.source = settings.HOSTNAME + "/posts/" + str(new_post.id.hex)
        new_post.origin = settings.HOSTNAME + "/posts/" + str(new_post.id.hex)
        new_post.save()

        # Take the user uid's passed in and convert them into Authors to set as the visibleTo list
        uids = post.getlist('visibleTo')
        visible_authors = Author.objects.filter(uid__in=uids)
        for author in visible_authors:
            new_post.visibleTo.add(author)

        # Categories is commented out because it's not yet in the post data, uncomment once available
        for category in post['categories'].split('\r\n'):
            try:
                # Try connecting to existing categories
                cat_object = Category.objects.get(name=category)
            except Category.DoesNotExist as e:
                cat_object = Category.objects.create(
                    name=category)  # Create one if not
            new_post.categories.add(cat_object)    #: LIST,

        # for key in body.keys():
        #     print(f'{key}: {body[key]}')

        if len(request.FILES) > 0:
            # If they uploaded a file this is an ajax call and we need to return a JSON response
            return JsonResponse({
                'success': 'true',
                'msg': new_post.id.hex
            })
        else:
            return redirect("/")

    # Response to a server, servers are considered 'root' and get all posts except for 'SERVERONLY'  and unlisted because
    # they have no reason to see those ones.
    def api_response(request, posts, pager, pagination_uris):
        size = min(int(request.GET.get('size', DEFAULT_PAGE_SIZE)), 50)
        output = {
            "query": "posts",
            "count": pager.count,
            "size": size,
            "posts": [post.to_api_object() for post in posts]
        }
        (prev_uri, next_uri) = pagination_uris
        if prev_uri:
            output['prev'] = prev_uri
        if next_uri:
            output['next'] = next_uri
        return JsonResponse(output)

    # Response for a local user, will get all the posts that the user can see, including friends, and foaf
    def retrieve_posts(request):
        # own post
        own_post = Post.objects.filter(
            author_id=request.user.uid, unlisted=False)

        # visibility =  PUBLIC
        public_post = Post.objects.filter(visibility="PUBLIC", unlisted=False)

        # visibility = FRIENDS
        users_friends = []
        friends = Friend.objects.filter(author_id=request.user.uid)
        for friend in friends:
            users_friends.append(friend.friend_id)
        friend_post = Post.objects.filter(
            author__in=users_friends, visibility="FRIENDS", unlisted=False)

        # visibility = FOAF
        FOAF_post = Post.objects.filter(visibility="FOAF", unlisted=False)
        foaf_post_id = []
        for post in FOAF_post:
            if FOAF_verification(request, post.author.uid):
                foaf_post_id.append(post.id)
        foaf_post = Post.objects.filter(id__in=foaf_post_id)

        # visibility = PRIVATE
        private_post = Post.objects.filter(
            visibleTo=request.user.uid, unlisted=False)

        # visibility = SERVERONLY
        local_host = request.user.host
        server_only_post = Post.objects.filter(
            author__host=local_host, visibility="SERVERONLY", unlisted=False)


        visible_post = public_post | foaf_post | friend_post | private_post | server_only_post | own_post

        visible_post = visible_post.distinct()

        array_of_posts = []
        count = visible_post.count()

        page_num = int(request.GET.get('page', "1"))
        size = min(int(request.GET.get('size', DEFAULT_PAGE_SIZE)), 50)

        for post in visible_post.order_by("-published"):
            author_id = Author.objects.get(uid=post.author_id)

            author_info = {
                "id": "http://" + str(author_id.uid),
                "email": str(author_id.email),
                "bio": str(author_id.bio),
                "host": str(author_id.host),
                "firstName": str(author_id.first_name),
                "lastName": str(author_id.last_name),
                "displayName": str(author_id.display_name),
                "url": str(author_id.url),
                "github": str(author_id.github)
            }

            categories = Category.objects.filter(post=post.id)
            categories_list = []
            for c in categories:
                categories_list.append(c.name)

            visible_to = post.visibleTo.all()
            visible_to_list = []
            for visible in visible_to:
                visible_to_list.append(visible.username)

            host = request.get_host()
            if request.is_secure():
                host = "https://" + host
            else:
                host = "http://" + host

            next_http = "{}/posts/{}/comments".format(host, post.id)
            comment_size, comments = get_comments(post.id)
            array_of_posts.append({
                "id": str(post.id),
                "title": str(post.title),
                "source": str(post.source),
                "origin": str(post.origin),
                "description": str(post.description),
                "contentType": str(post.contentType),
                "content": str(post.content),
                "author": author_info,
                "categories": categories_list,
                "count": int(comment_size),  # count of comment
                "size": int(size),
                "next": str(next_http),
                "comments": comments,  # return ~5
                "published": "{}+{}".format(post.published.strftime('%Y-%m-%dT%H:%M:%S'),
                                            str(post.published).split("+")[-1]),
                "visibility": str(post.visibility),
                "visibleTo": visible_to_list,
                "unlisted": post.unlisted
            })

        pager = Paginator(array_of_posts, size)

        uri = request.build_absolute_uri()

        if page_num > pager.num_pages:
            response_data = {
                "query": "posts",
                "count": int(count),
                "size": int(size),
                "previous": str(get_page_url(uri, pager.num_pages)),
                "posts": []

            }
            return JsonResponse(response_data)

        current_page = pager.page(page_num)

        if current_page.has_previous() and current_page.has_next():
            response_data = {
                "query": "posts",
                "count": int(count),
                "size": int(size),
                "next": str(get_page_url(uri, current_page.next_page_number())),
                "previous": str(get_page_url(uri, current_page.previous_page_number())),
                "posts": current_page.object_list
            }

        elif not current_page.has_next() and not current_page.has_previous():
            response_data = {
                "query": "posts",
                "count": int(count),
                "size": int(size),
                "posts": current_page.object_list
            }
        elif not current_page.has_next():
            response_data = {
                "query": "posts",
                "count": int(count),
                "size": int(size),
                "previous": str(get_page_url(uri, current_page.previous_page_number())),
                "posts": current_page.object_list
            }
        elif not current_page.has_previous():
            response_data = {
                "query": "posts",
                "count": int(count),
                "size": int(size),
                "next": str(get_page_url(uri, current_page.next_page_number())),
                "posts": current_page.object_list
            }

        return JsonResponse(response_data)

    if request.user.is_authenticated:
        return Endpoint(request, None, [
            Handler("POST", "application/json", create_new_post),
            Handler('GET', 'application/json', retrieve_posts)
        ]).resolve()
    else:
        auth = request.META['HTTP_AUTHORIZATION'].split()
        if len(auth) == 2:
            if auth[0].lower() == "basic":
                uname, passwd = base64.b64decode(
                    auth[1]).decode('utf-8').rsplit(':', 1)
        node = Node.objects.get(foreign_server_username=uname)

        if node.post_share and node.image_share:
            query = Post.objects.filter(unlisted=False).exclude(visibility="SERVERONLY").order_by("-published")
        elif node.post_share and not node.image_share:
            post_type = ["text/plain", "text/markdown"]
            query = Post.objects.filter(contentType__in=post_type,unlisted=False).exclude(visibility="SERVERONLY").order_by("-published")
        elif not node.post_share and node.image_share:
            post_type = ["image/png;base64", "image/jpeg;base64"]
            query = Post.objects.filter(contentType__in=post_type, unlisted=False).exclude(visibility="SERVERONLY").order_by(
                "-published")
        else:
            return JsonResponse({
                "success": False,
                "message": "Post and image sharing is turned off"
            }, status=403)

        return Endpoint(request, query,
                        [PagingHandler("GET", "application/json", api_response)]
                        ).resolve()
# Returns 5 newest comment on the post
def get_comments(post_id):
    comments_list = []
    comments = Comment.objects.filter(
        parentPost=post_id).order_by("-published")[:5]
    size = comments.count()

    for comment in comments:
        author = Author.objects.get(username=comment.author)
        c = {
            "id": str(comment.id),
            "contentType": str(comment.contentType),
            "comment": str(comment.content),
            "published": "{}+{}".format(comment.published.strftime('%Y-%m-%dT%H:%M:%S'),
                                        str(comment.published).split("+")[-1]),
            "author": {
                "id": "http://" + str(author.uid),
                "email": str(author.email),
                "bio": str(author.bio),
                "host": str(author.host),
                "firstName": str(author.first_name),
                "lastName": str(author.last_name),
                "displayName": str(author.display_name),
                "url": str(author.url),
                "github": str(author.github)
            }
        }
        comments_list.append(c)

    return size, comments_list


# https://stackoverflow.com/questions/5755150/altering-one-query-parameter-in-a-url-django
def get_page_url(request, page_number):

    (scheme, netloc, path, params, query, fragment) = urlparse(request)
    query_dict = QueryDict(query).copy()
    query_dict["page"] = page_number
    query = query_dict.urlencode()

    return urlunparse((scheme, netloc, path[:-1], params, query, fragment))


def post_edit_and_delete(request, post_id):
    # This endpoint REQUIRES that the individual accessing it is the original author of the Post in question.
    post = Post.objects.get(pk=post_id)

    if post.author != request.user:
        return HttpResponse("Forbidden: you must be the original author of the post in order to change it.", status=403)

    def get_edit_dialog(request):
        # REF: https://www.tangowithdjango.com/book/chapters/models_templates.html

        # Obtain the context from the HTTP request.
        context = RequestContext(request)

        # Query the database for a list of ALL categories currently stored.
        # Place the list in our context_dict dictionary which will be passed to the template engine.
        # @todo the above is not done, but if we implement a search or autocomplete it is unnecessary

        # Fill the context with the post in the request
        context_dict = {'post': post}

        # @todo THIS IS A HACK
        # The navigation template now requires the user object to be passed in to every view, but for some reason it
        # is not passed in unless we explicitly pass it in here.
        context_dict['user'] = request.user

        # Render the response and send it back!
        return render_to_response('editPost.html', context_dict, context)

    def edit_post(request):
        """
        Expects the request to contain all the variables defining a post to be provided by the POST vars.
        :param request:
        :return:
        """
        vars = request.POST
        for key in vars:
            if hasattr(post, key):
                if len(vars.getlist(key)) <= 1:  # Simple value or empty
                    try:
                        # Special fields
                        if key == 'categories':
                            post.categories.clear()
                            # Look up the categories or create them if they are new
                            categories = vars.get(key).split("\r\n")
                            for category in categories:
                                c, created = Category.objects.get_or_create(
                                    name=category)
                                post.categories.add(c)
                        else:
                            # All other fields
                            setattr(post, key, vars.get(key))
                    except Exception as e:
                        # @todo remove this try/except block.
                        #  This should ACTUALLY throw an error if we hit a problem here
                        print(
                            f"Unable to process key: {key}, it has value {vars.get(key)}")
                        pass
                elif len(vars.getlist(key)) > 1:  # Multiple values
                    # @todo implement handling multiple values for key
                    print("NOT IMPLEMENTED: Unable to handle multiple values for key")
        post.save()
        return JsonResponse({"success": "Post updated"})

    def delete_post(request):
        """
        We simply need to delete the post at this endpoint
        :param request:
        :return:
        """
        post.delete()
        return JsonResponse({"success": "Post Deleted"}, status=200)

    return Endpoint(request, None, [
        Handler('GET', 'text/html', get_edit_dialog),
        Handler('POST', 'application/json', edit_post),
        Handler('DELETE', 'application/json', delete_post)
    ]).resolve()


# http://service/author/{AUTHOR_ID}/posts
# (all posts made by {AUTHOR_ID} visible to the currently authenticated user)
@validate_remote_server_authentication()
def retrieve_posts_of_author_id_visible_to_current_auth_user(request, author_id):


    def api_response(request, posts, pager, pagination_uris):
        size = min(int(request.GET.get('size', DEFAULT_PAGE_SIZE)), 50)
        output = {
            "query": "posts",
            "count": pager.count,
            "size": size,
            "posts": [post.to_api_object() for post in posts]
        }
        (prev_uri, next_uri) = pagination_uris
        if prev_uri:
            output['prev'] = prev_uri
        if next_uri:
            output['next'] = next_uri
        return JsonResponse(output)

    def retrieve_author_posts(request):
        node = author_id.split("/author/")[0]
        id_of_author = author_id.split("/author/")[-1]
        try:
            valid_uuid = UUID(id_of_author, version=4)

        except ValueError:
            return JsonResponse({
                "success": False,
                "message": "Not a valid uuid"
            }, status=404)

        own_node = request.get_host()
        # Author is from different node
        if node != own_node:
            page_num = int(request.GET.get('page', "1"))
            size = min(int(request.GET.get('size', DEFAULT_PAGE_SIZE)), 50)

            request_size = 10
            diff_node = Node.objects.get(foreign_server_hostname=node)
            username = diff_node.username_registered_on_foreign_server
            password = diff_node.password_registered_on_foreign_server
            api = diff_node.foreign_server_api_location
            if diff_node.append_slash:
                api = api + "/"

            response = requests.get(
                "http://{}/author/{}/posts?size={}&page={}".format(api, author_id, request_size, page_num),
                auth=(username, password)
            )

            if response.status_code != 200:
                response_data = {
                    "query": "posts",
                    "count": 0,
                    "size": int(size),
                    "posts": []

                }
                return JsonResponse(response_data)

            posts_list = response.json()

            # grabbing all posts
            post_total_num = posts_list["count"]
            page = 2

            if len(posts_list["posts"]) > 0:
                total_post = [posts_list["posts"]]
            else:
                total_post = []
            total_post = total_post[0]

            while page <= math.ceil(post_total_num/request_size):
                response = requests.get(
                    "http://{}/author/{}/posts?size={}&page={}".format(api, author_id, request_size, page),
                    auth=(username, password)
                )
                posts_list = response.json()
                add_post = posts_list["posts"]
                total_post.append(add_post[0])
                page = page + 1

            viewable_post = []

            # "PUBLIC","FOAF","FRIENDS","PRIVATE"
            for i in range(len(total_post)):
                if total_post[i]["visibility"] == "PUBLIC":
                    viewable_post.append(total_post[i])
                if total_post[i]["visibility"] == "FOAF" and FOAF_verification(request, author_id):
                    viewable_post.append(total_post[i])
                if total_post[i]["visibility"] == "FRIENDS" and Friend.objects.filter(author_id=request.user.uid).filter(friend_id=author_id).exists():
                    viewable_post.append(total_post[i])
                if total_post[i]["visibility"] == "PRIVATE" and request.user.uid in total_post[i]["visibleTo"]:
                    viewable_post.append(total_post[i])

            count = len(viewable_post)
            pager = Paginator(viewable_post, size)
            uri = request.build_absolute_uri()

            if page_num > pager.num_pages:
                response_data = {
                    "query": "posts",
                    "count": int(count),
                    "size": int(size),
                    "previous": str(get_page_url(uri, pager.num_pages)),
                    "posts": []

                }
                return JsonResponse(response_data)

            current_page = pager.page(page_num)

            if current_page.has_previous() and current_page.has_next():
                response_data = {
                    "query": "posts",
                    "count": int(count),
                    "size": int(size),
                    "next": str(get_page_url(uri, current_page.next_page_number())),
                    "previous": str(get_page_url(uri, current_page.previous_page_number())),
                    "posts": current_page.object_list
                }
            elif not current_page.has_next() and not current_page.has_previous():
                response_data = {
                    "query": "posts",
                    "count": int(count),
                    "size": int(size),
                    "posts": current_page.object_list
                }
            elif not current_page.has_next():
                response_data = {
                    "query": "posts",
                    "count": int(count),
                    "size": int(size),
                    "previous": str(get_page_url(uri, current_page.previous_page_number())),
                    "posts": current_page.object_list
                }
            elif not current_page.has_previous():
                response_data = {
                    "query": "posts",
                    "count": int(count),
                    "size": int(size),
                    "next": str(get_page_url(uri, current_page.next_page_number())),
                    "posts": current_page.object_list
                }

            return JsonResponse(response_data)

        # Author in the same node
        else:
            try:
                author = Author.objects.get(id=id_of_author)
            except Author.DoesNotExist:
                return JsonResponse({
                    "success": False,
                    "message": "User does not exist"
                }, status=404)

            host = request.get_host()
            author_uid = host + "/author/" + str(id_of_author)

            if author_uid == request.user.uid:
                visible_post = Post.objects.filter(
                    author=author_uid, unlisted=False)

            else:
                # visibility =  PUBLIC
                public_post = Post.objects.filter(
                    author=author, visibility="PUBLIC", unlisted=False)

                # visibility = FRIENDS
                if Friend.objects.filter(author_id=author_uid).filter(friend_id=request.user.uid).exists():
                    friend_post = Post.objects.filter(
                        author=author, visibility__in=["FRIENDS", "FOAF"], unlisted=False)
                else:
                    friend_post = Post.objects.none()
                # CHECK
                if FOAF_verification(request, author_id):
                    foaf_post = Post.objects.filter(
                        author=author, visibility="FOAF", unlisted=False)
                else:
                    foaf_post = Post.objects.none()

                # visibility = PRIVATE
                private_post = Post.objects.filter(
                    author=author, visibleTo=request.user.uid, unlisted=False)

                # visibility = SERVERONLY
                if request.user.host == author.host:
                    server_only_post = Post.objects.filter(
                        author=author, visibility="SERVERONLY", unlisted=False)
                else:
                    server_only_post = Post.objects.none()

                visible_post = public_post | foaf_post | friend_post | private_post | server_only_post

            array_of_posts = []
            count = visible_post.count()
            page_num = int(request.GET.get('page', "1"))
            size = min(int(request.GET.get('size', DEFAULT_PAGE_SIZE)), 50)

            for post in visible_post.order_by("-published"):
                author = Author.objects.get(uid=post.author_id)
                author_info = {
                    "id": "http://" + str(author.uid),
                    "email": str(author.email),
                    "bio": str(author.bio),
                    "host": "http://"+str(author.host),
                    "firstName": str(author.first_name),
                    "lastName": str(author.last_name),
                    "displayName": str(author.display_name),
                    "url": "http://"+str(author.url),
                    "github": str(author.github)
                }

                categories = Category.objects.filter(post=post.id)
                categories_list = []
                for c in categories:
                    categories_list.append(c.name)

                visible_to = post.visibleTo.all()
                visible_to_list = []
                for visible in visible_to:
                    visible_to_list.append("http://" + visible.uid)

                next_http = "http:/{}/posts/{}/comments".format(host, post.id)

                comment_size, comments = get_comments(post.id)
                array_of_posts.append({
                    "id": str(post.id),
                    "title": str(post.title),
                    "source": str(post.source),
                    "origin": str(post.origin),
                    "description": str(post.description),
                    "contentType": str(post.contentType),
                    "content": str(post.content),
                    "author": author_info,
                    "categories": categories_list,
                    "count": int(comment_size),  # count of comment
                    "size": int(size),
                    "next": str(next_http),
                    "comments": comments,  # return ~5
                    "published": "{}+{}".format(post.published.strftime('%Y-%m-%dT%H:%M:%S'), str(post.published).split("+")[-1]),
                    "visibility": str(post.visibility),
                    "visibleTo": visible_to_list,
                    "unlisted": post.unlisted
                })

            pager = Paginator(array_of_posts, size)
            uri = request.build_absolute_uri()

            if page_num > pager.num_pages:
                response_data = {
                    "query": "posts",
                    "count": int(count),
                    "size": int(size),
                    "previous": str(get_page_url(uri, pager.num_pages)),
                    "posts": []

                }
                return JsonResponse(response_data)

            current_page = pager.page(page_num)

            if current_page.has_previous() and current_page.has_next():
                response_data = {
                    "query": "posts",
                    "count": int(count),
                    "size": int(size),
                    "next": str(get_page_url(uri, current_page.next_page_number())),
                    "previous": str(get_page_url(uri, current_page.previous_page_number())),
                    "posts": current_page.object_list
                }
            elif not current_page.has_next() and not current_page.has_previous():
                response_data = {
                    "query": "posts",
                    "count": int(count),
                    "size": int(size),
                    "posts": current_page.object_list
                }
            elif not current_page.has_next():
                response_data = {
                    "query": "posts",
                    "count": int(count),
                    "size": int(size),
                    "previous": str(get_page_url(uri, current_page.previous_page_number())),
                    "posts": current_page.object_list
                }
            elif not current_page.has_previous():
                response_data = {
                    "query": "posts",
                    "count": int(count),
                    "size": int(size),
                    "next": str(get_page_url(uri, current_page.next_page_number())),
                    "posts": current_page.object_list
                }

            return JsonResponse(response_data)

    if request.user.is_authenticated:
        return Endpoint(request, None, [
            Handler('GET', 'application/json', retrieve_author_posts)
        ]).resolve()
    else:
        auth = request.META['HTTP_AUTHORIZATION'].split()
        if len(auth) == 2:
            if auth[0].lower() == "basic":
                uname, passwd = base64.b64decode(
                    auth[1]).decode('utf-8').rsplit(':', 1)
        node = Node.objects.get(foreign_server_username=uname)

        if node.post_share and node.image_share:
            query = Post.objects.filter(author=author_id, unlisted=False).exclude(visibility="SERVERONLY").order_by("-published")
        elif node.post_share and not node.image_share:
            post_type = ["text/plain", "text/markdown"]
            query = Post.objects.filter(author=author_id, contentType__in=post_type, unlisted=False).exclude(
                visibility="SERVERONLY").order_by("-published")
        elif not node.post_share and node.image_share:
            post_type = ["image/png;base64", "image/jpeg;base64"]
            query = Post.objects.filter(author=author_id, contentType__in=post_type, unlisted=False).exclude(
                visibility="SERVERONLY").order_by(
                "-published")
        else:
            return JsonResponse({
                "success": False,
                "message": "Post and image sharing is turned off"
            }, status=403)

        return Endpoint(request, query, [
            PagingHandler("GET", "application/json", api_response)
        ]).resolve()


# Ida Hou

# author_id : (http://)localhost:8000/author/<UUID>

@validate_remote_server_authentication()
def friend_checking_and_retrieval_of_author_id(request, author_id):
    if request.method == 'POST':
        # ask a service if anyone in the list is a friend
        # POST to http://service/author/<authorid>/friends
        author_id = url_regex.sub('', author_id)

        body_unicode = str(request.body, 'utf-8')
        body = json.loads(body_unicode)

        potential_friends = body.get("authors", None)
        if not potential_friends:
            return HttpResponse("Post body missing fields", status=422)

        response_data = {}
        response_data["query"] = "friends"
        response_data["author"] = author_id
        response_data["authors"] = []
        if Friend.objects.filter(author_id=author_id).exists():
            for potential_friend in potential_friends:
                potential_friend = url_regex.sub('', potential_friend)
                if Friend.objects.filter(author_id=author_id).filter(friend_id=potential_friend).exists():
                    response_data["authors"].append(potential_friend)

        return JsonResponse(response_data)
    elif request.method == 'GET':
        # a reponse if friends or not
        # ask a service GET http://service/author/<authorid>/friends/
        # compose response data
        response_data = {}
        response_data['query'] = "friends"
        response_data['authors'] = []
        if Friend.objects.filter(author_id=author_id).exists():
            # get friend id from Friend table
            friends = Friend.objects.filter(
                author_id=author_id)

            for friend in friends:
                response_data['authors'].append(friend.friend_id)
        return JsonResponse(response_data)
    else:
        return HttpResponse("You can only GET or POST to the URL", status=405)

# Ida Hou
# Ask if 2 authors are friends
# GET http://service/author/<authorid>/friends/<authorid2>
# authorid : UUID
# authorid2: https://127.0.0.1%3A5454%2Fauthor%2Fae345d54-75b4-431b-adb2-fb6b9e547891 (url-encoded)


@validate_remote_server_authentication()
def check_if_two_authors_are_friends(request, author1_id, author2_id):
    if request.method == 'GET':
        # compose author id from author uid

        host = request.get_host()
        author1_id = host + "/author/" + str(author1_id)
        # decode + strip url protocol
        author2_id = url_regex.sub('', author2_id)

        # compose response data
        response_data = {}
        response_data["query"] = "friends"
        response_data["authors"] = [author1_id, author2_id]
        # query friend table for friendship information
        if Friend.objects.filter(author_id=author1_id).filter(friend_id=author2_id).exists():
            response_data["friends"] = True
        else:
            response_data["friends"] = False
        # add optional information of current user

        return JsonResponse(response_data)

    return HttpResponse("You can only GET the URL", status=405)


def post_creation_page(request):
    """
    Provide page that will allow a user to create a new post
    :param request:
    :return:
    """
    return render(request, 'posting.html', context={
        'post_retrieval_url': settings.HOSTNAME + reverse('post', args=['00000000000000000000000000000000']).replace('00000000000000000000000000000000/', '')
    })


def get_all_authors(request):
    """
    API to get a JSON of all authors in the system. To save space it will only provide:
    First, last and display names
    uid
    :param request:
    :return:
    """
    return JsonResponse({
        'success': True,
        'data': [author for author in Author.objects.values('first_name', 'last_name', 'display_name', 'uid')]
    })
