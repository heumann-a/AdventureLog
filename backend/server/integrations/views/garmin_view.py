from rest_framework.response import Response
from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
import logging
from datetime import datetime
from django.shortcuts import redirect
from django.conf import settings
from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)
from integrations.models import GarminToken

logger = logging.getLogger(__name__)


class GarminIntegrationView(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def _get_garmin_client(self, user):
        token = GarminToken.objects.filter(user=user).first()
        if not token or not token.session_data:
            return None, Response({
                'message': 'You need to authorize Garmin Connect first.',
                'error': True,
                'code': 'garmin.not_authorized'
            }, status=status.HTTP_403_FORBIDDEN)

        try:
            garmin = Garmin()
            garmin.client.loads(token.session_data)
            if not garmin.client.is_authenticated:
                return None, Response({
                    'message': 'Garmin Connect session expired. Please re-authorize.',
                    'error': True,
                    'code': 'garmin.session_expired'
                }, status=status.HTTP_401_UNAUTHORIZED)
            return garmin, None
        except Exception as e:
            logger.error(f"Error restoring Garmin session: {str(e)}")
            return None, Response({
                'message': 'Failed to restore Garmin session.',
                'error': True,
                'code': 'garmin.session_restore_failed'
            }, status=status.HTTP_502_BAD_GATEWAY)

    def _save_garmin_session(self, user, garmin, email):
        print(f"{garmin.client.dumps()}")
        session_data = garmin.client.dumps()
        GarminToken.objects.update_or_create(
            user=user,
            defaults={
                'email': email,
                'session_data': session_data,
            }
        )

    @action(detail=False, methods=['post'], url_path='authorize')
    def authorize(self, request):
        email = request.data.get('email')
        password = request.data.get('password')
        mfa_code = request.data.get('mfa_code')

        if not email or not password:
            return Response({
                'message': 'Email and password are required.',
                'error': True,
                'code': 'garmin.credentials_required'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            garmin = Garmin(
                email=email,
                password=password,
                is_cn=False,
                return_on_mfa=True
                )
            garmin.login()


            self._save_garmin_session(request.user, garmin, email)
            frontend_url = settings.FRONTEND_URL
            if not frontend_url.endswith('/'):
                frontend_url += '/'
            return Response({
                'message': 'Successfully connected to Garmin Connect.',
                'redirect_url': f"{frontend_url}settings?tab=integrations"
            }, status=status.HTTP_200_OK)


        except GarminConnectAuthenticationError as e:
            logger.warning(f"Garmin auth failed for user {request.user.username}: {str(e)}")
            return Response({
                'message': 'Invalid Garmin Connect credentials.',
                'error': True,
                'code': 'garmin.invalid_credentials'
            }, status=status.HTTP_401_UNAUTHORIZED)
        except GarminConnectTooManyRequestsError as e:
            logger.error(f"Garmin rate limit: {str(e)}")
            return Response({
                'message': 'Rate limit exceeded. Please wait before retrying.',
                'error': True,
                'code': 'garmin.rate_limited'
            }, status=status.HTTP_429_TOO_MANY_REQUESTS)
        except GarminConnectConnectionError as e:
            logger.error(f"Garmin connection error: {str(e)}")
            return Response({
                'message': 'Failed to connect to Garmin Connect.',
                'error': True,
                'code': 'garmin.connection_failed'
            }, status=status.HTTP_502_BAD_GATEWAY)
        except Exception as e:
            logger.error(f"Error during Garmin authorization: {str(e)}")
            return Response({
                'message': 'Failed to connect to Garmin Connect.',
                'error': True,
                'code': 'garmin.authorization_failed'
            }, status=status.HTTP_502_BAD_GATEWAY)

    @action(detail=False, methods=['get'], url_path='callback')
    def callback(self, request):
        frontend_url = settings.FRONTEND_URL
        if not frontend_url.endswith('/'):
            frontend_url += '/'
        return redirect(f"{frontend_url}settings?tab=integrations")

    @action(detail=False, methods=['post'], url_path='disable')
    def disable(self, request):
        token = GarminToken.objects.filter(user=request.user).first()
        if not token:
            return Response({
                'message': 'Garmin integration is not enabled for this user.',
                'error': True,
                'code': 'garmin.not_enabled'
            }, status=status.HTTP_404_NOT_FOUND)

        token.delete()
        return Response({
            'message': 'Garmin integration disabled successfully.'
        }, status=status.HTTP_204_NO_CONTENT)

    def refresh_garmin_session_if_needed(self, user):
        token = GarminToken.objects.filter(user=user).first()
        if not token or not token.session_data:
            return None, Response({
                'message': 'You need to authorize Garmin Connect first.',
                'error': True,
                'code': 'garmin.not_authorized'
            }, status=status.HTTP_403_FORBIDDEN)

        try:
            garmin = Garmin()
            garmin.client.loads(token.session_data)
            if not garmin.client.is_authenticated:
                return None, Response({
                    'message': 'Garmin Connect session expired. Please re-authorize.',
                    'error': True,
                    'code': 'garmin.session_expired'
                }, status=status.HTTP_401_UNAUTHORIZED)
            return garmin, None
        except Exception as e:
            logger.error(f"Error refreshing Garmin session: {str(e)}")
            return None, Response({
                'message': 'Failed to refresh Garmin session.',
                'error': True,
                'code': 'garmin.session_refresh_failed'
            }, status=status.HTTP_502_BAD_GATEWAY)

    def extract_essential_activity_info(self, activity):
        activity_id = activity.get('activityId')
        duration = activity.get('duration')
        if isinstance(duration, dict):
            duration = duration.get('value')
        distance = activity.get('distance')
        if isinstance(distance, dict):
            distance = distance.get('value')
        elevation_gain = activity.get('elevationGain')
        if isinstance(elevation_gain, dict):
            elevation_gain = elevation_gain.get('value')
        elevation_loss = activity.get('elevationLoss')
        if isinstance(elevation_loss, dict):
            elevation_loss = elevation_loss.get('value')

        average_speed = activity.get('averageSpeed')
        if isinstance(average_speed, dict):
            average_speed = average_speed.get('value')
        max_speed = activity.get('maxSpeed')
        if isinstance(max_speed, dict):
            max_speed = max_speed.get('value')

        average_hr = activity.get('averageHeartRate')
        if isinstance(average_hr, dict):
            average_hr = average_hr.get('value')
        max_hr = activity.get('maxHeartRate')
        if isinstance(max_hr, dict):
            max_hr = max_hr.get('value')

        calories = activity.get('calories')
        if isinstance(calories, dict):
            calories = calories.get('value')
        average_cadence = activity.get('averageCadence')
        if isinstance(average_cadence, dict):
            average_cadence = average_cadence.get('value')

        start_lat = activity.get('startLatitude')
        start_lng = activity.get('startLongitude')
        end_lat = activity.get('endLatitude')
        end_lng = activity.get('endLongitude')

        start_latlng = None
        end_latlng = None
        if start_lat is not None and start_lng is not None:
            start_latlng = [float(start_lat), float(start_lng)]
        if end_lat is not None and end_lng is not None:
            end_latlng = [float(end_lat), float(end_lng)]

        avg_speed_ms = average_speed
        max_speed_ms = max_speed
        avg_speed_kmh = round(avg_speed_ms * 3.6, 2) if avg_speed_ms else None
        avg_speed_mph = round(avg_speed_ms * 2.237, 2) if avg_speed_ms else None
        max_speed_kmh = round(max_speed_ms * 3.6, 2) if max_speed_ms else None
        max_speed_mph = round(max_speed_ms * 2.237, 2) if max_speed_ms else None

        pace_per_km = None
        pace_per_mile = None
        if duration and distance and distance > 0:
            pace_per_km = duration / (distance / 1000)
            pace_per_mile = duration / (distance / 1609.34)

        distance_km = round(distance / 1000, 2) if distance else None
        distance_miles = round(distance / 1609.34, 2) if distance else None

        timezone = None
        timezone_raw = None
        tz_data = activity.get('timeZoneUnitDTO')
        if tz_data:
            timezone_raw = str(tz_data)
            timezone = tz_data.get('timeZone')

        return {
            "id": activity_id,
            "name": activity.get('activityName'),
            "type": activity.get('activityType', {}).get('typeKey') if isinstance(activity.get('activityType'), dict) else activity.get('activityType'),
            "sport_type": activity.get('activityType', {}).get('typeKey') if isinstance(activity.get('activityType'), dict) else activity.get('activityType'),
            "distance": distance,
            "distance_km": distance_km,
            "distance_miles": distance_miles,
            "moving_time": duration,
            "elapsed_time": activity.get('elapsedDuration', duration),
            "rest_time": None,
            "total_elevation_gain": elevation_gain,
            "estimated_elevation_loss": elevation_loss,
            "elev_high": activity.get('elevationMax'),
            "elev_low": activity.get('elevationMin'),
            "total_elevation_range": None,
            "start_date": activity.get('startTimeGMT'),
            "start_date_local": activity.get('startTimeLocal'),
            "timezone": timezone,
            "timezone_raw": timezone_raw,
            "average_speed": avg_speed_ms,
            "average_speed_kmh": avg_speed_kmh,
            "average_speed_mph": avg_speed_mph,
            "max_speed": max_speed_ms,
            "max_speed_kmh": max_speed_kmh,
            "max_speed_mph": max_speed_mph,
            "pace_per_km_seconds": pace_per_km,
            "pace_per_mile_seconds": pace_per_mile,
            "grade_adjusted_average_speed": None,
            "average_cadence": average_cadence,
            "average_watts": activity.get('averagePower'),
            "max_watts": activity.get('maxPower'),
            "kilojoules": None,
            "calories": calories,
            "achievement_count": None,
            "kudos_count": None,
            "comment_count": None,
            "pr_count": None,
            "gear_id": None,
            "device_name": activity.get('deviceName'),
            "trainer": activity.get('indoor') or False,
            "manual": activity.get('manual') or False,
            "start_latlng": start_latlng,
            "end_latlng": end_latlng,
            "export_original": None,
            "export_gpx": None,
            "visibility": None,
            "photo_count": 0,
            "has_heartrate": average_hr is not None,
            "flagged": False,
            "commute": activity.get('commute') or False,
        }

    @action(detail=False, methods=['get'], url_path='activities')
    def activities(self, request):
        garmin, error_response = self.refresh_garmin_session_if_needed(request.user)
        if error_response:
            return error_response

        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        limit = request.query_params.get('limit', 20)
        page = request.query_params.get('page', 0)

        try:
            if start_date and end_date:
                start_parsed = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                end_parsed = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                activities = garmin.get_activities_by_date(
                    startdate=start_parsed.strftime('%Y-%m-%d'),
                    enddate=end_parsed.strftime('%Y-%m-%d'),
                )
            else:
                activities = garmin.get_activities(
                    start=int(page),
                    limit=min(int(limit), 100),
                )

            if activities is None:
                activities = []

            essential_activities = [self.extract_essential_activity_info(act) for act in activities]

            return Response({
                'activities': essential_activities,
                'count': len(essential_activities),
                'page': int(page),
                'limit': int(limit)
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error fetching Garmin activities: {str(e)}")
            return Response({
                'message': 'Failed to fetch activities from Garmin Connect.',
                'error': True,
                'code': 'garmin.fetch_failed'
            }, status=status.HTTP_502_BAD_GATEWAY)

    @action(detail=False, methods=['get'], url_path='activities/(?P<activity_id>[^/.]+)')
    def activity(self, request, activity_id=None):
        if not activity_id:
            return Response({
                'message': 'Activity ID is required.',
                'error': True,
                'code': 'garmin.activity_id_required'
            }, status=status.HTTP_400_BAD_REQUEST)

        garmin, error_response = self.refresh_garmin_session_if_needed(request.user)
        if error_response:
            return error_response

        try:
            activity = garmin.get_activity(str(activity_id))
            essential_activity = self.extract_essential_activity_info(activity)
            return Response(essential_activity, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error fetching Garmin activity: {str(e)}")
            return Response({
                'message': 'Failed to fetch activity from Garmin Connect.',
                'error': True,
                'code': 'garmin.fetch_failed'
            }, status=status.HTTP_502_BAD_GATEWAY)
