from django.urls import path

from . import views


urlpatterns = [
    path("", views.index, name="strava-gen"),
    path("health/", views.health, name="health"),
]
