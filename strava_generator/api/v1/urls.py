from django.urls import path

from . import views

urlpatterns = [
    path("route", views.route, name="api-v1-route"),
    path("search-location", views.search_location, name="api-v1-search-location"),
    path("generate-strava-gpx", views.get_generated_strava_gpx, name="api-v1-generate-strava-gpx"),
]
