# Generated by Django 2.2.9 on 2020-02-17 18:34

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('authors', '0001_initial'),
        ('posts', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Category',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=256, unique=True)),
            ],
        ),
        migrations.AddField(
            model_name='post',
            name='visibleTo',
            field=models.ManyToManyField(related_name='posts_granted_access_to', to='authors.Author'),
        ),
        migrations.AlterField(
            model_name='post',
            name='visibility',
            field=models.CharField(choices=[('PUBLIC', 'Public'), ('FOAF', 'Friends of Friends'), ('FRIENDS', 'Friends'), ('PRIVATE', 'Private'), ('SERVERONLY', 'Server Admins Only')], default='FRIENDS', max_length=16),
        ),
        migrations.AddField(
            model_name='post',
            name='categories',
            field=models.ManyToManyField(to='posts.Category'),
        ),
    ]