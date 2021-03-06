from django.contrib import admin
# Register your models here
from .models import Friend, FriendRequest

# custom friend admin to have a filter box which provides filter by author_id
# Author : Ida Hou
# Implementation of requirement : "As an author, my server will know about my friends" Issue #38


class CustomFriendAdmin(admin.ModelAdmin):
    list_filter = ['author_id']
    list_display = ['author_id', 'friend_id']


admin.site.register(Friend, CustomFriendAdmin)
admin.site.register(FriendRequest)
