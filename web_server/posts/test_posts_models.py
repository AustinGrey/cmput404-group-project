import uuid
from datetime import datetime
from django.test import TestCase, Client, override_settings
from users.models import Author
from posts.models import Post,VisibleTo
from django.urls import reverse


#This is the unit test for post model
@override_settings(HOSTNAME="127.0.0.1:8000")
class TestPostsModels(TestCase):

    def setUp(self):
        id1 = uuid.uuid5(uuid.NAMESPACE_DNS, 'test1').hex
        id_str1 = str(id1)
        Author.objects.create(id=id1, username='test1', display_name="TestPostModels1", email="author1@test.com", password="password1",
                              first_name="firstname1",
                              last_name="lastname1", bio="authortest1.com", github="github1.com", is_active=True,
                              host="127.0.0.1:8000", is_superuser=False,
                              is_staff="False", uid="127.0.0.1:8000/author/" + id_str1,
                              url="http://127.0.0.1:8000/author/" + id_str1,
                              date_joined=datetime(year=2020, month=2, day=26))

        id = uuid.uuid5(uuid.NAMESPACE_DNS, 'test2').hex
        id_str = str(id)
        # uid = "127.0.0.1:8000/author/" + id_str
        author_test = Author.objects.create(id=id, username='test2', display_name="TestPostModels2", email="author2@test.com", password="password2",
                              first_name="firstname2",
                              last_name="lastname2", bio="authortest2.com", github="github2.com", is_active=True,
                              host="127.0.0.1:8000", is_superuser=False,
                              is_staff="False", uid="127.0.0.1:8000/author/" + id_str,
                              url="http://127.0.0.1:8000/author/" + id_str,
                              date_joined=datetime(year=2020, month=2, day=26))


        post_id=uuid.uuid5(uuid.NAMESPACE_DNS, 'post').hex
        post = Post.objects.create(id=post_id, contentType="text/plain",title="Post Unit Test", source="post@unittest.ca",
                            origin="post@unittest.ca",description="This is a unit test.", content="This is a unit test of Post model.",
                            visibility="FRIENDS", author=Author.objects.get(id=id1),size=1)

        VisibleTo.objects.create(author_uid=author_test.uid,accessed_post=post)


    def test_data(self):
        post_id = uuid.uuid5(uuid.NAMESPACE_DNS, 'post').hex
        post_test = Post.objects.get(id=post_id)

        self.assertEqual(post_test.id.hex, post_id)
        self.assertEqual(post_test.contentType, "text/plain")
        self.assertEqual(post_test.title, "Post Unit Test")
        self.assertEqual(post_test.source,"post@unittest.ca")
        self.assertEqual(post_test.origin, "post@unittest.ca")
        self.assertEqual(post_test.description, "This is a unit test.")
        self.assertEqual(post_test.content, "This is a unit test of Post model.")
        self.assertEqual(post_test.visibility, "FRIENDS")
        self.assertEqual(post_test.author.id.hex,uuid.uuid5(uuid.NAMESPACE_DNS, 'test1').hex)
        self.assertEqual(post_test.size, 1)


    def test_to_api_object(self):
        post_id = uuid.uuid5(uuid.NAMESPACE_DNS, 'post').hex
        post_test=Post.objects.get(id=post_id)
        returndict=post_test.to_api_object()
        id1 = uuid.uuid5(uuid.NAMESPACE_DNS, 'test1').hex
        id_str1 = str(id1)

        self.assertEqual(returndict['id'],post_id)
        self.assertEqual(returndict["title"],"Post Unit Test")
        self.assertEqual(returndict["source"],"post@unittest.ca")
        self.assertEqual(returndict["origin"], "post@unittest.ca")
        self.assertEqual(returndict["description"],"This is a unit test.")
        self.assertEqual(returndict["contentType"],"text/plain")
        self.assertEqual(returndict["content"],"This is a unit test of Post model.")
        self.assertEqual(returndict["visibility"], "FRIENDS")
        self.assertEqual(returndict["author"]["id"], "https://127.0.0.1:8000/author/"+id_str1)
        self.assertEqual(returndict["size"],1)
        self.assertEqual(returndict["visibility"],"FRIENDS")
        self.assertEqual(returndict["visibleTo"][0], "http://"+Author.objects.get(id=uuid.uuid5(uuid.NAMESPACE_DNS, 'test2').hex).uid)
