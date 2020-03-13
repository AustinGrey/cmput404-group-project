# Generated by Django 2.2.10 on 2020-03-08 20:00

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('friendship', '0003_follow'),
    ]

    operations = [
        migrations.AlterField(
            model_name='follow',
            name='followee_id',
            field=models.CharField(max_length=500),
        ),
        migrations.AlterField(
            model_name='follow',
            name='follower_id',
            field=models.CharField(max_length=500),
        ),
        migrations.AlterField(
            model_name='friend',
            name='author_id',
            field=models.CharField(max_length=500),
        ),
        migrations.AlterField(
            model_name='friend',
            name='friend_id',
            field=models.CharField(max_length=500),
        ),
        migrations.AlterField(
            model_name='friendrequest',
            name='from_id',
            field=models.CharField(max_length=500),
        ),
        migrations.AlterField(
            model_name='friendrequest',
            name='to_id',
            field=models.CharField(max_length=500),
        ),
    ]
