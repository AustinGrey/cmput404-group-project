# cmput404-group-project
Group project for the 404, team EarlyBirds

Website URL: https://cmput404-group-project-mandala.herokuapp.com/

This project is now archived. It was for a university assignment and while a worthwhile exercise has little continuing value.

# Documentation
### Documentation can be found on our GitHub Wiki or from the links below
[Endpoint Documentation](https://github.com/AustinGrey/cmput404-group-project/wiki/Endpoints-Documentation)<br>
[Front End Documentation](https://github.com/AustinGrey/cmput404-group-project/wiki/Front-End-Documentation)<br>
[UI Storyboard](https://github.com/AustinGrey/cmput404-group-project/wiki/UI-Storyboard)<br>

# Test Data
## Creating Test Data
The following command will create a copy of your database and dump it into a file for others to load

    python manage.py dumpdata --indent 2 --format yaml > test_data.yaml

## Loading Test Data
The following command will load the file created in the above command into your database

    python manage.py loaddata test_data.yaml

# Testcases
## Model Class Unittest
    python3 manage.py test friendship.tests.TestFriendshipModels
    python3 manage.py test comments.test_comment_models
    python3 manage.py test users.tests.TestAuthorModels
    python3 manage.py test posts.test_posts_models
    
    
# Ajax Documentation
## Usage of axios
    post.html, editPost.html, profile.html, home.html 

	In editPost.html fetch is used to send the form data to edit the current post and on success returns to homepage and on failure, alerts the user.

	In post.html jquery and ajax is used to send any images to our image proxy endpoint and replace the image source with the base64 of that image.

	In profile.html axios is used to retrieve a users info, friends and github activity

	In home.html axios is used to retrieve the list of local and foreign post
