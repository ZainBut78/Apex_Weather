# ExternalAPICallLog.api_type ki choices mein "images" add kiya gaya
# (Pexels calls log ho rahi thi magar choice list mein nahi thi).
# Yeh sirf Django-side metadata hai — sqlmigrate is pe (no-op) dikhata hai.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("weather", "0006_city_image_url"),
    ]

    operations = [
        migrations.AlterField(
            model_name="externalapicalllog",
            name="api_type",
            field=models.CharField(
                choices=[
                    ("forecast", "Live Forecast"),
                    ("archive", "Historical Archive"),
                    ("geocoding", "Geocoding"),
                    ("images", "City Images (Pexels)"),
                ],
                max_length=20,
            ),
        ),
    ]
