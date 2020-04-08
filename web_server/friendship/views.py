from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
from friendship.models import FriendRequest, Friend
from nodes.models import Node
from django.contrib.auth.decorators import login_required
import json
import re
from nodes.models import Node
import base64
import requests
from uuid import UUID
from social_distribution.utils.basic_auth import validate_remote_server_authentication
from urllib.parse import quote
url_regex = re.compile(r"(http(s?))?://")

# strip protocol, trailing slash and remove dashes uuid


def sanitize_author_id(author_id):
    author_id = url_regex.sub('', author_id).rstrip("/")
    splits = author_id.rsplit("/", 1)
    try:
        author_id_formatted = splits[0] + "/" + UUID(splits[1]).hex
        return author_id_formatted
    except:
        return author_id


"""
INTERNAL ENDPOINT
endpoint: http://service/friendrequest/handle

allowed methods: 
POST: accepts the friend request
DELETE: rejects the friend request
requires same request body content as http://service/friendrequest

response status:
405: method not allowed 
422: request body missing fields 
409: conflict: pre-existing frienship 
200: friendrequest rejected
201: friendship established


"""


def handle_friend_request(request):
    # handle friend request acception
    if request.method != "POST" and request.method != "DELETE":
        return HttpResponse("Method not Allowed", status=405)

    body = request.body.decode('utf-8')
    body = json.loads(body)
    from_id = body.get("author", {}).get("id", None)
    from_host = body.get("author", {}).get("host", None)
    from_host = url_regex.sub("", from_host).rstrip("/").split("/")[0]
    to_id = body.get("friend", {}).get("id", None)
    to_host = body.get("friend", {}).get("host", None)
    to_host = url_regex.sub('', to_host).rstrip("/")
    if not from_id or not to_id or not from_host or not to_host:
        # Unprocessable Entity
        return HttpResponse("post request body missing fields", status=422)

    # strip protocol
    from_id = sanitize_author_id(from_id)
    to_id = sanitize_author_id(to_id)

    if request.method == 'POST':

        if FriendRequest.objects.filter(from_id=from_id).filter(to_id=to_id).exists():

            # delete the entry in FriendRequest
            FriendRequest.objects.filter(
                from_id=from_id).filter(to_id=to_id).delete()

            if Friend.objects.filter(author_id=from_id).filter(friend_id=to_id).exists():
                return HttpResponse("Friendship already exists!", status=409)
            # if B accepts A's friend request, then B and A are friends
            new_friend = Friend(author_id=from_id, friend_id=to_id)
            new_friend.save()
            new_friend = Friend(author_id=to_id, friend_id=from_id)
            new_friend.save()
            # if request is from remote author
            # we need to send friend request back as "confirmation"
            # if from_host != request.get_host():

            # return send_friend_request_to_foreign_friend(body.get("author"), body.get("friend"), from_host)

            return HttpResponse("Friend successfully added", status=201)
        else:
            return HttpResponse("No such friend request", status=404)

    # handle friend request rejection
    elif request.method == 'DELETE':
        if FriendRequest.objects.filter(from_id=from_id).filter(to_id=to_id).exists():
            # delete the entry in FriendRequest
            FriendRequest.objects.filter(
                from_id=from_id).filter(to_id=to_id).delete()
            return HttpResponse("Friend request successfully rejected", status=200)
        else:
            return HttpResponse("No such friend request", status=404)


"""
this function calls foreign_server's http://service/friendrequest endpoint
"""


def send_friend_request_to_foreign_friend(friend_info, author_info, foreign_server):

    if not Node.objects.filter(foreign_server_hostname=foreign_server).exists():
        return HttpResponse("Not Authenticated with Remote Server", status=401)
    node = Node.objects.get(foreign_server_hostname=foreign_server)

    data = {}
    data["query"] = "friendrequest"
    data["author"] = author_info
    data["friend"] = friend_info
    json_data = json.dumps(data)
    headers = {'Content-Type': 'application/json'}
    url = "http://{}/friendrequest".format(
        node.foreign_server_api_location.rstrip("/"))
    if node.append_slash:
        url += "/"
    response = requests.post(
        url, headers=headers, auth=(node.username_registered_on_foreign_server, node.password_registered_on_foreign_server), data=json_data)

    return HttpResponse(response.text, status=response.status_code)


"""
PUBLIC ENDPOINT
endpoint: http://service/friendrequest 

allowed methods: 
POST: to make a friend request 


response status:
401: authentication required 
405: method not allowed 
422: request body missing fields 
409: conflict: friend request already existed 
201: friendrequest sent 


"""


@validate_remote_server_authentication()
def send_friend_request(request):
    # Make a friend request
    if request.method == 'POST':
        # parse request body
        body = request.body.decode('utf-8')
        body = json.loads(body)
        from_id = body.get("author", {}).get("id", None)
        from_host = body.get("author", {}).get("host", None)
        to_id = body.get("friend", {}).get("id", None)
        to_host = body.get("friend", {}).get("host", None)
        if not from_id or not to_id or not from_host or not to_host:
            # Unprocessable Entity
            return HttpResponse("post request body missing fields", status=422)
        # strip protocol and remove dash
        from_id = sanitize_author_id(from_id)
        to_id = sanitize_author_id(to_id)

        # if friend request already existed
        if FriendRequest.objects.filter(from_id=from_id).filter(to_id=to_id).exists():

            return HttpResponse("Friend Request Already exists", status=409)
        # strip protocol for hostname
        from_host = url_regex.sub('', from_host).rstrip("/")
        to_host = url_regex.sub('', to_host).rstrip("/").split("/")[0]
        # if friendship already existed
        if Friend.objects.filter(author_id=from_id).filter(friend_id=to_id).exists():
            return HttpResponse("Friendship already exists!", status=409)
        # handle outgoing request from local author
        if from_host == request.get_host():
            # friend request from local author to local author
            if to_host != request.get_host():
                # retrieve basic auth credential from Node table
                http_response = send_friend_request_to_foreign_friend(
                    body.get("friend"), body.get("author"), to_host)
                if http_response.status_code >= 200 and http_response.status_code < 300:
                    if not FriendRequest.objects.filter(from_id=from_id).filter(to_id=to_id).exists():
                        new_request = FriendRequest(
                            from_id=from_id, to_id=to_id)
                        new_request.save()
                        return HttpResponse("Friend Request Successfully sent", status=201)
                    return HttpResponse("Friend Request Already Sent", status=409)
                else:
                    return http_response
            else:
                new_request = FriendRequest(from_id=from_id, to_id=to_id)
                new_request.save()

            return HttpResponse("Friend Request Successfully sent", status=201)
        # handle incoming friend request from remote server
        else:
            # now foreign author B is sending local author A an FriendRequest, However, on our local system
            # there is already FriendRequest sent from A to B.
            # that's means that B accepted A's request and B is sending A "confirmation request"
            # this case, we should just delete FriendRequest entry from A to B and friend A and B

            if FriendRequest.objects.filter(from_id=to_id).filter(to_id=from_id).exists():
                FriendRequest.objects.filter(
                    from_id=to_id).filter(to_id=from_id).delete()
                new_friend = Friend(author_id=from_id, friend_id=to_id)
                new_friend.save()
                new_friend = Friend(author_id=to_id, friend_id=from_id)
                new_friend.save()

                return HttpResponse("{} and {} become friend".format(from_id, to_id), status=201)
            # this is a pure friend request from remote author B to local author A -> create an entry in FriendRequest table
            # pending for local author A to handle
            else:
                new_request = FriendRequest(from_id=from_id, to_id=to_id)
                new_request.save()
                return HttpResponse("Friend Request Successfully sent", status=201)

        return HttpResponse("Friend Request Successfully sent", status=201)

    return HttpResponse("You can only POST to the URL", status=405)


"""
INTERNAL ENDPOINT
endpoint: http://service/friendrequest/<author_id: UUID>

allowed methods: 
GET: return a list of friendrequest sent to the current author 


response:
200: success
401: authentication required 


example response: 
{
    "query": "retrieve_friend_requests",
    "author": "127.0.0.1:8000/author/c730cf54a83d4d0982ec13a578692793",
    "request": [
       "http://host3/author/de305d54-75b4-431b-adb2-eb6b9e546013",
       "http://host2/author/ae345d54-75b4-431b-adb2-fb6b9e547891"
      ]
}
    
"""


def retrieve_friend_request_of_author_id(request, author_id):
    if request.method == "GET":
        # construct full url of author id

        host = request.get_host()
        author_id = host + "/author/" + str(author_id)

        response_data = {}
        response_data["query"] = "retrieve_friend_requests"
        response_data["author"] = author_id
        # a list of author ids who send friend request to current author_id
        response_data["request"] = []
        if FriendRequest.objects.filter(to_id=author_id).exists():
            # get friend id from Friend table
            requests = FriendRequest.objects.filter(
                to_id=author_id)
            for request in requests:
                response_data["request"].append(request.from_id)
        return JsonResponse(response_data, status=200)

    return HttpResponse("You can only GET the URL", status=405)


"""
invalidate outgoing friend requests of an author by calling foreign servers'
https://service/authorid/friend/authorid2 endpoint
"""


def invalidate_friend_requests(author_id):
    author_id = url_regex.sub('', author_id)
    author_id = author_id.rstrip("/")
    if not FriendRequest.objects.filter(from_id=author_id).exists():
        return

    friend_requests = FriendRequest.objects.filter(from_id=author_id)

    hostname = author_id.split("/")[0]
    for request in friend_requests:
        to_host = request.to_id.split("/")[0]

        # foreign requests -> call foreign server endpoint to validate
        if hostname != to_host:
            if Node.objects.filter(pk=to_host).exists():
                node = Node.objects.get(foreign_server_hostname=to_host)
                # quoted_author_id = quote(
                #     author_id, safe='~()*!.\'')
                headers = {"Content-Type": "application/json",
                           "Accept": "application/json"}
                url = "https://{}/friends/{}".format(request.to_id, author_id)
                res = requests.get(url, headers=headers, auth=(
                    node.username_registered_on_foreign_server, node.password_registered_on_foreign_server))
                if res.status_code >= 200 and res.status_code < 300:
                    res = res.json()
                    # if they are friends
                    if res["friends"]:
                        if FriendRequest.objects.filter(from_id=author_id).filter(to_id=request.to_id).exists():
                            FriendRequest.objects.filter(from_id=author_id).filter(
                                to_id=request.to_id).delete()
                            if not Friend.objects.filter(author_id=author_id).filter(friend_id=request.to_id).exists():
                                new_friend = Friend(
                                    author_id=author_id, friend_id=request.to_id)
                                new_friend.save()
                                new_friend = Friend(
                                    author_id=request.to_id, friend_id=author_id)
                                new_friend.save()
                    # delete if they are not friends yet
                    else:
                        pending = res.get("pending", None)
                        if pending is False:
                            if FriendRequest.objects.filter(from_id=author_id).filter(to_id=request.to_id).exists():
                                FriendRequest.objects.filter(from_id=author_id).filter(
                                    to_id=request.to_id).delete()


# FOAF verification involves the 3 hosts of the 3 friends A->B->C
# assuming A B C reside on different hosts.
# and in the same server

def FOAF_verification(request, author):
    auth_user = request.user.uid
    auth_user = url_regex.sub("", auth_user).rstrip("/")
    author = url_regex.sub("", author).rstrip("/")

    own_node = request.get_host()
    if auth_user == author:
        return True


    # If the author is a friend of auth user return True
    if Friend.objects.filter(author_id=auth_user).filter(friend_id=author).exists():
        return True


    # author is the person that made the post
    # auth user is the person trying to get the post
    # author has a friend B
    # auth user has friend B
    # there fore FOAF
    # get the friends of the auth_user (person trying to comment)
    # and check if there is a friendship between the friend of the auth_user with the author (person that made the post)
    friends = []

    auth_user_node = auth_user.split("/author")[0]
    if auth_user_node == own_node:
        # getting friends of authorized user
        auth_user_friends = Friend.objects.filter(author_id=auth_user)
        for friend in auth_user_friends:
            friends.append(friend.friend_id)


    else:
        try:
            node_object = Node.objects.get(foreign_server_hostname=auth_user_node)
        except Node.DoesNotExist as e:
            # If we do not know their friends node, then we must not try to connect with it,
            # But we can still consult other friends
            print(f"Attempt to FOAF verify friend node hostname '{auth_user_node}' but we do not have access to that node.")
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

    return Friend.objects.filter(author_id=author).filter(friend_id__in=friends).exists()


