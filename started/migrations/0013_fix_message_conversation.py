# Generated migration to fix Message model

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('started', '0012_add_verification_code_field'),
    ]

    operations = [
        # Ensure conversation field exists and is properly linked
        migrations.RunSQL(
            "UPDATE started_message SET conversation_id = 1 WHERE conversation_id IS NULL;",
            reverse_sql=migrations.RunSQL.noop
        ),
    ]