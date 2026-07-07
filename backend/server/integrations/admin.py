from django.contrib import admin
from allauth.account.decorators import secure_admin_login

from .models import ImmichIntegration, StravaToken, GarminToken, WandererIntegration

admin.autodiscover()
admin.site.login = secure_admin_login(admin.site.login)

admin.site.register(ImmichIntegration)
admin.site.register(StravaToken)
admin.site.register(GarminToken)
admin.site.register(WandererIntegration)