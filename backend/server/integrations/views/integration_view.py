import os
from rest_framework.response import Response
from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from integrations.models import ImmichIntegration, StravaToken, GarminToken, WandererIntegration
from django.conf import settings
from garminconnect import Garmin, GarminConnectTooManyRequestsError


class IntegrationView(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    def list(self, request):
        """
        RESTful GET method for listing all integrations.
        """
        immich_integrations = ImmichIntegration.objects.filter(user=request.user)
        google_map_integration = settings.GOOGLE_MAPS_API_KEY != ''
        strava_integration_global = settings.STRAVA_CLIENT_ID != '' and settings.STRAVA_CLIENT_SECRET != ''
        strava_integration_user = StravaToken.objects.filter(user=request.user).exists()
        garmin_integration_user = GarminToken.objects.filter(user=request.user).first()
        is_garmin_expired = False
        if garmin_integration_user:
            try:
                garmin = Garmin()
                garmin.client.loads(garmin_integration_user.session_data)
                garmin_integration_user = garmin.client.is_authenticated
            except GarminConnectTooManyRequestsError:
                is_garmin_expired = True

        wanderer_integration = WandererIntegration.objects.filter(user=request.user).exists()
        is_wanderer_expired = False

        if wanderer_integration:
            token_expiry = WandererIntegration.objects.filter(user=request.user).first().token_expiry
            if token_expiry and token_expiry < timezone.now():
                is_wanderer_expired = True

        return Response(
            {
                'immich': immich_integrations.exists(),
                'google_maps': google_map_integration,
                'strava': {
                    'global': strava_integration_global,
                    'user': strava_integration_user
                },
                'garmin': {
                    'user': garmin_integration_user,
                    'expired': is_garmin_expired
                },
                'wanderer': {
                    'exists': wanderer_integration,
                    'expired': is_wanderer_expired
                }
            },
            status=status.HTTP_200_OK
        )
