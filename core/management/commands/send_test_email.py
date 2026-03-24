from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Send a test email using the configured email backend."

    def add_arguments(self, parser):
        parser.add_argument("recipient", help="Email address to send the test email to")

    def handle(self, *args, **options):
        recipient = options["recipient"].strip()
        if not recipient:
            raise CommandError("Recipient email is required.")

        sent_count = send_mail(
            subject="ClubsHub email test",
            message=(
                "Hello,\n\n"
                "This is a test email from ClubsHub.\n"
                "If you received this email, SMTP is configured correctly.\n\n"
                "Regards,\n"
                "ClubsHub"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )

        if sent_count != 1:
            raise CommandError(f"Expected to send 1 email, but sent {sent_count}.")

        self.stdout.write(
            self.style.SUCCESS(f"Test email sent successfully to {recipient}")
        )
