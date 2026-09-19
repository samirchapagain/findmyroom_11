# Generated migration to add verification_code field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('started', '0011_populate_conversations'),
    ]

    operations = [
        migrations.AddField(
            model_name='clientpayment',
            name='verification_code',
            field=models.CharField(blank=True, max_length=6, null=True),
        ),
    ]