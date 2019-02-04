# -*- coding: utf-8 -*-
# Generated by Django 1.11.18 on 2019-01-31 16:34
from __future__ import unicode_literals

from django.db import migrations, models
import jsonfield.fields


class Migration(migrations.Migration):

    dependencies = [
        ('icds_reports', '0088_child_name'),
    ]

    operations = [
        migrations.CreateModel(
            name='CCZHosting',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('identifier', models.CharField(max_length=255, unique=True)),
                ('app_versions', jsonfield.fields.JSONField(default=dict)),
                ('username', models.CharField(max_length=255)),
                ('password', models.CharField(max_length=255)),
            ],
        ),
    ]
