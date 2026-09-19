# Generated migration to fix Message model

from django.db import migrations


def repair_message_conversations(apps, schema_editor):
    Message = apps.get_model('started', 'Message')
    Conversation = apps.get_model('started', 'Conversation')
    Client = apps.get_model('started', 'Client')
    Owner = apps.get_model('started', 'Owner')

    for message in Message.objects.filter(conversation__isnull=True).select_related(
        'room', 'sender', 'receiver'
    ):
        client = Client.objects.filter(
            user_id__in=(message.sender_id, message.receiver_id)
        ).first()
        owner = Owner.objects.filter(
            user_id__in=(message.sender_id, message.receiver_id)
        ).first()
        if not client or not owner or message.room.owner_id != owner.id:
            continue

        conversation, _ = Conversation.objects.get_or_create(
            client_id=client.id,
            owner_id=owner.id,
            room_id=message.room_id,
        )
        message.conversation_id = conversation.id
        message.save(update_fields=['conversation'])


def reverse_repair_message_conversations(apps, schema_editor):
    Message = apps.get_model('started', 'Message')
    Message.objects.update(conversation=None)


class Migration(migrations.Migration):

    dependencies = [
        ('started', '0012_add_verification_code_field'),
    ]

    operations = [
        migrations.RunPython(
            repair_message_conversations,
            reverse_repair_message_conversations,
        ),
    ]