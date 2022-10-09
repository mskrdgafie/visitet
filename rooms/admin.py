from django.contrib import admin
from .models import Room, RoomType, Photo

# Register your models here.

admin.site.register(RoomType)
admin.site.register(Room)
admin.site.register(Photo)