from django.shortcuts import render, redirect
from django.http import HttpResponse, HttpResponseNotAllowed, HttpResponseRedirect, JsonResponse
from django.contrib.auth import login
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .forms import UserRegisterForm
from django.contrib.auth import views as auth_views
from django.urls import reverse
from friendship.models import Friend
from nodes.models import Node
import requests
from users.models import Author
from django.conf import settings
from uuid import uuid4

from json import loads

from nodes.models import Node
from friendship.views import invalidate_friend_requests
import requests
from social_distribution.utils.basic_auth import validate_remote_server_authentication
import re
# used for stripping url protocol
url_regex = re.compile(r"(http(s?))?://")


class CustomLogin(auth_views.LoginView):
    def form_valid(self, form):
        login(self.request, form.get_user())
        # set expiration of the current login session
        # a single login is alive for 10hrs
        self.request.session.set_expiry(36000)
        return HttpResponseRedirect(self.get_success_url())


@login_required
def profile(request, user_id):
    """
    Local handler for viewing author profiles, the author in question might be local or foreign,
    both should be supported
    """
    stripped_user_id = url_regex.sub("", user_id).rstrip("/")

    if Author.is_uid_local(stripped_user_id):
        # @todo , this template expects a uuid in order to render, it should be able to handle a uid
        invalidate_friends(request.get_host(), stripped_user_id)
        invalidate_friend_requests(stripped_user_id)
        return render(request, 'users/profile.html', {
            'user_id': Author.extract_uuid_from_uid(stripped_user_id),  # uuid
            'user_full_id': stripped_user_id,  # uid

            'post_view_url': reverse('view_post', args=['00000000000000000000000000000000']).replace('00000000000000000000000000000000/', '')
        })

    return render(request, 'users/profile.html', {
        'user_id': Author.extract_uuid_from_uid(stripped_user_id),  # uuid
        'user_full_id': stripped_user_id,  # uid
        'post_view_url': reverse('view_post', args=[stripped_user_id])


    })


"""
 this function invalidates existing friendship of give author 
 it GETs foreign servers' https://service/<authorid: UUID>/friends/<authorid2:: URL> endpoint to retrieve latest 
 friendship status (if given author has foreign friends)
"""


def invalidate_friends(host, user_id):
    author_id = url_regex.sub('', user_id)
    author_id = author_id.rstrip("/")
    if not Friend.objects.filter(author_id=author_id).exists():
        return
    friends = Friend.objects.filter(author_id=author_id)
    for friend in friends:
        splits = friend.friend_id.split("/")
        friend_host = splits[0]
        if host != friend_host:
            if Node.objects.filter(pk=friend_host).exists():
                node = Node.objects.get(foreign_server_hostname=friend_host)
                headers = {"Content-Type": "application/json",
                           "Accept": "application/json"}
                url = "https://{}/friends/{}".format(
                    friend.friend_id, author_id)
                res = requests.get(url, headers=headers, auth=(
                    node.username_registered_on_foreign_server, node.password_registered_on_foreign_server))
                if res.status_code >= 200 and res.status_code < 300:
                    res = res.json()
                    # if they are friends
                    pending = res.get("pending", None)
                    if not pending and not res["friends"]:
                        if Friend.objects.filter(author_id=author_id).filter(friend_id=friend.friend_id).exists():
                            Friend.objects.filter(author_id=author_id).filter(
                                friend_id=friend.friend_id).delete()
                            Friend.objects.filter(author_id=friend.friend_id).filter(
                                friend_id=author_id).delete()

@login_required
def view_post(request, post_path):
    """
    Local handler for viewing a post, the post might be local or foreign, and the path should determine that.
    The first part of the path should be a hostname, and the last part should be the post id
    If no hostname is provided (no path, only a uuid), then the local server is assumed
    """
    path = post_path.split('/')
    host = path[0]
    post_id = path[-1]

    # Assume local server if only uuid provided
    if len(path) == 1:
        return redirect('post', args=[path[0]])

    # Redirect if local post
    if host == settings.HOSTNAME:
        # Local post, handle as normal by redirecting them to the current post viewer
        return redirect(reverse('post', args=[post_id]))

    # Foreign post
    # Find the node this post is associated with
    try:
        node = Node.objects.get(foreign_server_hostname=host)
    except Node.DoesNotExist as e:
        return HttpResponse(f"No foreign server with hostname {host} is registered on our server.", status=404)

    req = node.make_api_get_request(f'posts/{post_id}')

    # Attempt to extract the post, theres a lot of different interpretations of the spec floating out there.
    # Some return bare posts, some return it under a different key
    while True:
        try:
            # Spec compliant
            post = req.json()['posts'][0]
            break
        except:
            pass
        try:
            # Bare post in proper key
            post = req.json()['posts']
            break
        except:
            pass
        try:
            # Incorrect key missing an s
            post = req.json()['post']
            break
        except:
            pass
        try:
            # Bare post
            post = req.json()
            break
        except:
            return HttpResponse("We attempted to grab the post from the foreign server, but the response was not"
                                f"understandable. The response looks like: {req.content[:20]}",
                                status=500)
        break

    # Some of the servers are incorrectly using 'content_type' instead of 'contentType'
    if 'content_type' in post and 'contentType' not in post:
        post['contentType'] = post['content_type']


    # Attempt to render the post
    try:
        # For image posts, we create a special content for direct rendering as an image
        post['image_content_data'] = 'data:' + post['contentType'] + ',' + post['content']

        return render(request, 'posts/foreign_post.html', {
            'post': post
        })
    except Exception as e:
        print(post)
        return HttpResponse(f"The post you are trying to view is on a foreign server, which responded unexpectedly: {post}"
                            f". Which is missing values: {e}",
                            status=500)

@login_required
def view_post_comment(request, post_path):
    """
    Local handler for viewing a post, the post might be local or foreign, and the path should determine that.
    The first part of the path should be a hostname, and the last part should be the post id
    If no hostname is provided (no path, only a uuid), then the local server is assumed
    """
    path = post_path.split('/')
    host = path[0]
    post_id = path[-1]
    # Assume local server if only uuid provided
    if len(path) == 1:
        return redirect('post', args=[path[0]])

    # Redirect if local post
    if host == settings.HOSTNAME:
        # Local post, handle as normal by redirecting them to the current post viewer
        return redirect(reverse('post', args=[post_id]))

    # Foreign post
    # Find the node this post is associated with
    try:
        node = Node.objects.get(foreign_server_hostname=host)
    except Node.DoesNotExist as e:
        return HttpResponse(f"No foreign server with hostname {host} is registered on our server.", status=404)

    if request.method == "GET":
        req = node.make_api_get_request(f'posts/{post_id}/comments')
        comments_list = []
        for comment in req.json()["comments"]:
            content = {
                "author": comment["author"],
                "content": comment["comment"],
                "contentType": comment["contentType"],
                "published": comment["published"],
                "id": comment["id"]
            }
            comments_list.append(content)

        output = {
            "query": "comments",
            "count": req.json()["count"],
            "size": req.json()["size"],
            "comments": comments_list
        }

        return JsonResponse(output)

    elif request.method == "POST" and host != settings.HOSTNAME:
        body = request.body.decode('utf-8')
        comment_info = loads(body)
        comment_info = comment_info['comment']

        # author_uid = "{}/author/{}".format(settings.HOSTNAME, comment_info["author"]["id"].replace("-", ""))
        author_uid = url_regex.sub("", comment_info["author"]["id"]).rstrip("/")
        author = Author.objects.get(uid=author_uid)
        output = {
            "query": "addComment",
            "post": "http://"+post_path,
            "comment": {
                "author": author.to_api_object(),
                "comment": comment_info["comment"],
                "contentType": comment_info['contentType'],
                "published": comment_info['published'],
                "id": str(uuid4())
            }
        }
        try:
            node = Node.objects.get(foreign_server_hostname=host)
        except Node.DoesNotExist as e:
            return HttpResponse(f"No foreign server with hostname {host} is registered on our server.", status=404)

        api = node.foreign_server_api_location
        api = "http://{}/posts/{}/comments".format(api, post_id)
        if node.append_slash:
            api = api + "/"
        response = requests.post(api,
            auth=(node.username_registered_on_foreign_server, node.password_registered_on_foreign_server),
            json=output
        )

        return HttpResponse(response.text, status=response.status_code)


@login_required
def add_friend(request):
    return render(request, 'users/add_friend.html')


def register(request):
    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            # wait for admin permission to activate account
            user.is_active = False
            host = request.get_host()
            url = host + "/author/" + str(user.id.hex)
            # set user url
            user.url = url
            # set user id
            # format: 127.0.0.1:5454/author/de305d54-75b4-431b-adb2-eb6b9e546013
            user.uid = url
            # set user host
            user.host = host

            # update database entry of current user
            user.save()
            return redirect('login')

    else:
        form = UserRegisterForm()
    return render(request, 'users/register.html', {'form': form})


def mandala(request):
    return render(request, 'users/mandala.html')
