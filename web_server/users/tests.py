import uuid
from datetime import datetime

from django.test import TestCase, Client, override_settings
from users.models import Author
from django.urls import reverse
from dateutil import tz

class TestViews(TestCase):
    def setUp(self):

        self.register_url = reverse('register')
        self.login_url = reverse('login')
        self.client = Client()

    def test_user_signup(self):
        new_user_information = {
            "username": "aNewUserForTesting",
            "email": "aNewUserForTesting@gmail.com",
            "password1": "aPassword!",
            "password2": "aPassword!",
            "first_name": "firstname",
            "last_name": "lastname",

        }
        response = self.client.post(
            self.register_url, data=new_user_information)
        # check response code
        self.assertEquals(response.status_code, 302)
        self.assertTrue(Author.objects.filter(
            username="aNewUserForTesting").exists())
        new_user = Author.objects.get(username="aNewUserForTesting")
        self.assertEquals(new_user.first_name, "firstname")
        self.assertEquals(new_user.last_name, "lastname")
        self.assertEquals(new_user.email, "aNewUserForTesting@gmail.com")

        self.assertTrue(new_user.uid)
        self.assertFalse(new_user.is_active)
        self.assertTrue(new_user.id)
        self.assertEquals(new_user.uid, new_user.url)
        Author.objects.get(username="aNewUserForTesting").delete()


#This is the unit test for author model
@override_settings(HOSTNAME="127.0.0.1:8000")
class TestAuthorModels(TestCase):

    def setUp(self):
        id = uuid.uuid5(uuid.NAMESPACE_DNS, 'test').hex
        id_str = str(id)
        Author.objects.create(id = id,display_name="TestAuthorModels",email="author@test.com",password="password1", first_name="firstname",
            last_name="lastname",bio="authortest.com", github="github.com", is_active=True,host="127.0.0.1:8000", is_superuser=False,
                              is_staff="False",uid="127.0.0.1:8000/author/"+id_str,url="http://127.0.0.1:8000/author/"+id_str,
                              date_joined=datetime(year=2020, month=2, day=26, hour=8, minute=30))



    def test_data(self):
        id = uuid.uuid5(uuid.NAMESPACE_DNS, 'test').hex
        id_str = str(id)
        display_name = "TestAuthorModels"
        email = "author@test.com"
        password = "password1"
        first_name = "firstname"
        last_name = "lastname"
        bio = "authortest.com"
        github = "github.com"
        is_active = True
        host = "127.0.0.1:8000"
        is_superuser = False
        is_staff = False
        uid = "127.0.0.1:8000/author/" + id_str
        date_joined = datetime(year=2020, month=2, day=26, hour=8, minute=30)

        author_test = Author.objects.get(id=id)
        self.assertEqual(author_test.id.hex, id)
        self.assertEqual(author_test.date_joined.astimezone(tz.tzlocal()), date_joined.astimezone(tz.tzlocal()))
        self.assertEqual(author_test.display_name,display_name)
        self.assertEqual(author_test.email,email)
        self.assertEqual(author_test.password, password)
        self.assertEqual(author_test.first_name, first_name)
        self.assertEqual(author_test.last_name, last_name)
        self.assertEqual(author_test.bio, bio)
        self.assertEqual(author_test.github, github)
        self.assertEqual(author_test.is_active, is_active)
        self.assertEqual(author_test.host, host)
        self.assertEqual(author_test.is_superuser, is_superuser)
        self.assertEqual(author_test.is_staff, is_staff)
        self.assertEqual(author_test.uid, uid)
        self.assertEqual(author_test.url, "http://127.0.0.1:8000/author/" + id_str)

    def test_author_is_uid_local(self):
        id = uuid.uuid5(uuid.NAMESPACE_DNS, 'test').hex
        id_str = str(id)
        uid = "127.0.0.1:8000/author/" + id_str
        author_test = Author.objects.get(id = id)

        self.assertEqual(author_test.is_uid_local(uid),True)

    def test_author_extract_uuid_from_uid(self):
        id = uuid.uuid5(uuid.NAMESPACE_DNS, 'test').hex
        author_test = Author.objects.get(id=id)
        id_str = str(id)
        uid = "127.0.0.1:8000/author/" + id_str

        self.assertEqual(author_test.extract_uuid_from_uid(uid), id_str)

    def test_to_api_object(self):
        id = uuid.uuid5(uuid.NAMESPACE_DNS, 'test').hex
        author_test = Author.objects.get(id=id)
        id_str = str(id)
        uid = "127.0.0.1:8000/author/" + id_str
        host = "127.0.0.1:8000"
        display_name = "TestAuthorModels"
        github = "github.com"
        test_dic = {
            "id": "https://"+uid,
            "host": "https://"+host,
            "displayName": display_name,
            "url": "https://"+uid,
            "github": github
        }

        return_dict = author_test.to_api_object()
        self.assertEqual(return_dict['id'], test_dic['id'])
        self.assertEqual(return_dict['host'], test_dic['host'])
        self.assertEqual(return_dict['displayName'], test_dic['displayName'])
        self.assertEqual(return_dict['url'], test_dic['url'])
        self.assertEqual(return_dict['github'], test_dic['github'])

