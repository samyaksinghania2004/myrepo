ClubsHub auth update bundle

Included:
- Email verification after signup
- "This was not me" report/deactivate flow
- Resend verification page
- Email OTP login
- Forgot-password templates
- Admin updates
- Tests
- Migration files

Apply on server:
1. Unzip this bundle over the project root.
2. Activate the venv and source .env.
3. Run:
   python manage.py makemigrations accounts
   python manage.py migrate
   python manage.py test accounts
   python manage.py runserver 0.0.0.0:8000

Manual checks:
- Sign up with a new IITK email
- Open the verification email and click verify
- Try the "not me" link for another signup
- Confirm unverified users cannot login with password
- Confirm verified users can login with password and OTP
- Confirm forgot password still sends reset email
