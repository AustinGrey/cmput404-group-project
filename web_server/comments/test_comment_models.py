import uuid
from datetime import datetime
from django.test import TestCase, Client, override_settings
from users.models import Author
from posts.models import Post
from comments.models import Comment
from dateutil import tz

class TestCommentModels(TestCase):

    def setUp(self):
        comment_id=uuid.uuid5(uuid.NAMESPACE_DNS, 'comment').hex
        post_id = uuid.uuid5(uuid.NAMESPACE_DNS, 'post').hex
        id = uuid.uuid5(uuid.NAMESPACE_DNS, 'author').hex
        id_str = str(id)

        author=Author.objects.create(id=id, username='author', display_name="TestCommentModels",
                                            email="author2@test.com", password="password2",
                                            first_name="firstname2",
                                            last_name="lastname2", bio="authortest2.com", github="github2.com",
                                            is_active=True,
                                            host="127.0.0.1:8000", is_superuser=False,
                                            is_staff="False", uid=self.get_author_uid(),
                                            url="http://127.0.0.1:8000/author/" + id_str,
                                            date_joined=datetime(year=2020, month=2, day=26))

        post = Post.objects.create(id=post_id, contentType="text/plain", title="Post Unit Test",
                                   source="post@unittest.ca",
                                   origin="post@unittest.ca", description="This is a unit test.",
                                   content="This is a unit test of Post model.",
                                   visibility="FRIENDS", author=Author.objects.get(id=id), size=1)


        Comment.objects.create(contentType="text/markdown", content="This is a comment model unit test.",id=comment_id,
                              author=author.uid, parentPost=post)

    def get_author_uid(self):
        id = uuid.uuid5(uuid.NAMESPACE_DNS, 'author').hex
        id_str = str(id)
        return "127.0.0.1:8000/author/" + id_str

    def test_data(self):
        comment_id = uuid.uuid5(uuid.NAMESPACE_DNS, 'comment').hex
        comment_test=Comment.objects.get(id=comment_id)
        published = datetime.now().date()

        self.assertEqual(comment_test.contentType, "text/markdown")
        self.assertEqual(comment_test.content, "This is a comment model unit test.")
        self.assertEqual(comment_test.author, self.get_author_uid())
        self.assertEqual(comment_test.parentPost.id.hex, uuid.uuid5(uuid.NAMESPACE_DNS, 'post').hex)
        self.assertEqual(comment_test.published.astimezone(tz.tzlocal()).date(), published)


    def test_to_api_object(self):
        comment_id = uuid.uuid5(uuid.NAMESPACE_DNS, 'comment').hex
        comment=Comment.objects.get(id=comment_id)
        returndict = comment.to_api_object()
        published = datetime.now().date()

        self.assertEqual(returndict['id'], comment_id)
        self.assertEqual(returndict["author"]["id"], "https://"+self.get_author_uid())
        self.assertEqual(returndict["published"].astimezone(tz.tzlocal()).date(), published)
        self.assertEqual(returndict["contentType"], "text/markdown")
        self.assertEqual(returndict["comment"], "This is a comment model unit test.")
