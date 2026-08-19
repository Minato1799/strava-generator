from django.urls import include, path


urlpatterns = [
    path("", include("strava_generator.urls")),
    path("api/", include("strava_generator.api.urls")),
]
