from django.db import models
from django.contrib.auth.hashers import make_password

import requests


# Create your models here.
#


"""
Node Model: to store credential information used to authenticate foreign servers 


SCHEMA: 
CREATE TABLE IF NOT EXISTS "nodes_node" 
("foreign_server_hostname" varchar(500) NOT NULL PRIMARY KEY, 
"foreign_server_username" varchar(500) NOT NULL UNIQUE, 
"foreign_server_password" varchar(500) NOT NULL, 
"foreign_server_api_location" varchar(500) NOT NULL, 
"username_registered_on_foreign_server" varchar(500) NOT NULL, 
"password_registered_on_foreign_server" varchar(500) NOT NULL, 
"image_share" bool NOT NULL, "append_slash" bool NOT NULL, "post_share" bool NOT NULL);


example:
http://dsnfof.herokuapp.com/
from hostname ->  Authentication: basic server_username:server_password
hostname = "dsnfof.herokuapp.com"
server_username = "their username"
server_password = "password"
we send -> to api_location Authentication: api_username:api_password
api_location = "dsnfof.herokuapp.com/api"
api_username = "our username"
api_password = "some password"

"""

# As a server admin, I want to be able to add node to share with #44


class Node(models.Model):

    foreign_server_hostname = models.CharField(
        primary_key=True, max_length=500, unique=True)

    # the credentials this foreign server use to log into our server
    foreign_server_username = models.CharField(
        max_length=500, null=False, unique=True)
    foreign_server_password = models.CharField(max_length=500, null=False)

    foreign_server_api_location = models.CharField(max_length=500, null=False)
    # the credentials our server use to log into this foreign server
    username_registered_on_foreign_server = models.CharField(
        max_length=500)
    password_registered_on_foreign_server = models.CharField(
        max_length=500)

    # As a server admin, I want to share or not share images with users on other servers. #5
    image_share = models.BooleanField(default=False)

    # As a server admin, I want to share or not share posts with users on other servers. #6
    post_share = models.BooleanField(default=False)

    append_slash = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        # make_password hashes the password
        self.foreign_server_password = make_password(
            self.foreign_server_password)
        # self.password_registered_on_foreign_server = make_password(
        #     self.password_registered_on_foreign_server)=

        super(Node, self).save(*args, **kwargs)

    def get_safe_api_url(self, path=''):
        """
        Returns a url that will access this Node's API location.
        Abstracts away choices like if a slash should be appended, or what protocol to use
        """
        api_url = self.foreign_server_api_location

        # Strip away any protocol prefixes that may have accidentally been specified
        api_url = api_url[8:] if api_url[:8] == 'https://' else api_url
        api_url = api_url[7:] if api_url[:7] == 'http://' else api_url

        # Strip away any remaining leading or trailing slashes that may have been specified for the api or path
        api_url = api_url.strip('/')
        stripped_path = path.strip('/')

        # Construct the desired api path
        api_url = f'http://{api_url}/{stripped_path}'

        if self.append_slash:
            api_url += "/"

        return api_url

    def make_api_get_request(self, path=''):
        """
        Gets the appropriate API url based on the path, and then makes a request against it.
        Automatically authenticates.
        Returns the requests library response, it is not otherwise processed
        """
        url = self.get_safe_api_url(path)
        req = requests.get(url,
                           auth=(self.username_registered_on_foreign_server,
                                 self.password_registered_on_foreign_server),
                           headers={'Accept': 'application/json'})
        return req
