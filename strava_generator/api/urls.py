from django.urls import include, path

urlpatterns = [
    path("v1/", include("strava_generator.api.v1.urls")),
]
