from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from . import models as m


@admin.register(m.User)
class LogisUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Merchant", {"fields": ("merchant",)}),)
    list_display = ("username", "email", "merchant", "is_staff")


for model in [m.Merchant, m.PincodeZone, m.Product, m.Courier, m.RateCard, m.Customer, m.Order, m.OrderItem,
              m.Shipment, m.TrackingEvent, m.InvoiceLine, m.CodRemittance]:
    admin.site.register(model)
