# Generated by Django 2.2.10 on 2020-03-23 21:43

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nodes', '0003_auto_20200322_2208'),
    ]

    operations = [
        migrations.AlterField(
            model_name='node',
            name='foreign_server_api_location',
            field=models.URLField(max_length=500),
        ),
    ]
