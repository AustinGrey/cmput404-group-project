from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, JsonResponse

from .models import Post
from comments.models import Comment
from users.models import Author
from nodes.models import Node

from json import loads
from django.core import serializers

from social_distribution.utils.endpoint_utils import Endpoint, PagingHandler, Handler

import requests


# @login_required
def retrieve_all_public_posts_on_local_server(request):
    """
    For endpoint http://service/posts
    Retrieves all public posts located on the server
    Methods: GET
    :param request: should specify Accepted content-type
    :returns: application/json | text/html
    """
    def json_handler(request, posts, pager, pagination_uris):
        # Use Django's serializers to encode the posts as a python object
        json_posts = loads(serializers.serialize('json', posts))

        # Explicitly add authors to the serialization
        author_exclude_fields = ('password',"is_superuser", "is_staff", "groups", "user_permissions")
        json_authors = loads(serializers.serialize('json_e', [post.author for post in posts], exclude_fields=author_exclude_fields))
        for i in range(0, len(json_posts)):
            json_posts[i]['fields']['author'] = json_authors[i]['fields']  # avoid inserting the meta data

            # As per the specification, get the 5 most recent comments
            comments = Comment.objects.filter(parentPost=posts[i])[:5]
            comments_json = loads(serializers.serialize('json', comments))
            comments_author_json = loads(serializers.serialize('json_e', [comment.author for comment in comments], exclude_fields=author_exclude_fields))
            # Explicitly add authors to the comments
            for j in range(0, len(comments_json)):
                comments_json[j]['fields']['author'] = comments_author_json[i]['fields']  # avoid inserting meta data
            # Strip meta data from each comment
            comments_json = [comment['fields'] for comment in comments_json]
            json_posts[i]['fields']['comments'] = comments_json


        # And filter out the meta data from the top level object
        for post in json_posts:
            post['fields']['id'] = post['pk']
        json_posts = [post['fields'] for post in json_posts]

        output = {
            "query": "posts",
            "count": pager.count,
            "size": len(posts),
            "posts": json_posts
        }
        (prev_uri, next_uri) = pagination_uris
        if prev_uri:
            output['prev'] = prev_uri
        if next_uri:
            output['next'] = next_uri

        return JsonResponse(output)

    def html_handler(request, posts, pager, pagination_uris):
        (prev_uri, next_uri) = pagination_uris

        return render(request, 'posts/stream.html')


    endpoint = Endpoint(request,
                        Post.objects.filter(visibility="PUBLIC"),
                        [
                            PagingHandler("GET", "text/html", html_handler),
                            PagingHandler("GET", "application/json", json_handler)
                        ])

    return endpoint.resolve()

# access to a single post with id = {POST_ID}
# http://service/posts/{POST_ID} 
def retrieve_single_post_with_id(request, post_id):
    def json_handler(request, posts, pager, pagination_uris):
        # Use Django's serializers to encode the posts as a python object
        json_posts = loads(serializers.serialize('json', posts))

        # Explicitly add authors to the serialization
        author_exclude_fields = ('password',"is_superuser", "is_staff", "groups", "user_permissions")
        json_authors = loads(serializers.serialize('json_e', [post.author for post in posts], exclude_fields=author_exclude_fields))
        for i in range(0, len(json_posts)):
            json_posts[i]['fields']['author'] = json_authors[i]['fields']  # avoid inserting the meta data

            # As per the specification, get the 5 most recent comments
            comments = Comment.objects.filter(parentPost=posts[i])[:5]
            comments_json = loads(serializers.serialize('json', comments))
            comments_author_json = loads(serializers.serialize('json_e', [comment.author for comment in comments], exclude_fields=author_exclude_fields))
            # Explicitly add authors to the comments
            for j in range(0, len(comments_json)):
                comments_json[j]['fields']['author'] = comments_author_json[i]['fields']  # avoid inserting meta data
            # Strip meta data from each comment
            comments_json = [comment['fields'] for comment in comments_json]
            json_posts[i]['fields']['comments'] = comments_json


        # And filter out the meta data from the top level object
        for post in json_posts:
            post['fields']['id'] = post['pk']
        json_posts = [post['fields'] for post in json_posts]

        output = {
            "query": "getPost",
            "post": json_posts
        }
        (prev_uri, next_uri) = pagination_uris
        if prev_uri:
            output['prev'] = prev_uri
        if next_uri:
            output['next'] = next_uri

        return JsonResponse(output)

    def html_handler(request, posts, pager, pagination_uris):
        post = Post.objects.get(id=post_id)
        #print(post.categories.all())
        # post = get_object_or_404(Post, pk=post_id)
        # for c in post.categories:
        #     print(c)
        return render(request, 'posts/post.html', {'post': post})

    # Get a single post
    endpoint = Endpoint(request,
                        Post.objects.filter(id=post_id),
                        [
                            PagingHandler("GET", "text/html", html_handler),
                            PagingHandler("GET", "application/json", json_handler)
                        ])

    return endpoint.resolve()


def comments_retrieval_and_creation_to_post_id(request, post_id):
    def get_handler(request, posts, pager, pagination_uris):
        # Explicitly add authors to the serialization
        author_exclude_fields = ('password',"is_superuser", "is_staff", "groups", "user_permissions")

        # Get the comments
        comments = Comment.objects.filter(parentPost=posts[0])
        comments_json = loads(serializers.serialize('json', comments))
        comments_author_json = loads(serializers.serialize('json_e', [comment.author for comment in comments], exclude_fields=author_exclude_fields))
        # Explicitly add authors to the comments
        for j in range(0, len(comments_json)):
            comments_json[j]['fields']['author'] = comments_author_json[j]['fields']  # avoid inserting meta data
        # Strip meta data from each comment
        for comment in comments_json:
            comment['fields']['id'] = comment['pk']
        comments_json = [comment['fields'] for comment in comments_json]

        output = {
            "query": "comments",
            "count": pager.count,
            "size": len(posts),
            "comments": comments_json
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
            "query": "addComment"
        }
        try:
            body = request.POST
            comment_info = loads(body['comment'])
            new_comment = Comment()
            new_comment.contentType = comment_info['contentType']
            new_comment.comment = comment_info['comment']
            new_comment.published = comment_info['published']
            new_comment.author = Author.objects.filter(id=comment_info['author']['id']).first()
            new_comment.parentPost = Post.objects.filter(id=post_id).first()
            new_comment.save()
            output['type'] = True
            output['message'] = "Comment added"
        except Exception as e:
            output['type'] = False
            output['message'] = "Comment not allowed"
            output['error'] = str(e)
        finally:
            return JsonResponse(output)

    return Endpoint(request, Post.objects.filter(id=post_id), [
                        Handler("POST", "application/json", post_handler),
                        PagingHandler("GET", "application/json", get_handler)
                    ]).resolve()


@login_required  # Local server usage only
def fetch_public_posts_from_nodes(request):
    """
    Fetches public posts from all the nodes available to the server
    :param request:
    :return:
    """
    output = {
        'query': "getPosts",
        'size': 10,
        'count': 0,
        'posts': []
    }
    for node in Node.objects.all():
        # Get the url of the api
        api_url = 'http://' + node.foreign_server_api_location
        if api_url[-1] == '/':
            # Remove trailing slash if there is one
            api_url = api_url[:-1]
        api_url += "/posts"

        response = requests.get(api_url,
                                auth=(node.foreign_server_username, node.foreign_server_password),
                                headers={'Accept': 'application/json'})
        if response.status_code != 200:
            print(f"Failure to get posts from {node.foreign_server_hostname}, "
                  f"received response code {response.status_code} at api endpoint: {api_url}")
            continue

        json = response.json()
        for post in json['posts']:
            output['count'] += 1
            output['posts'].append(post)
            if output['count'] >= output['size']:
                break

        if output['count'] >= output['size']:
            break

    return JsonResponse(output, status=200)


