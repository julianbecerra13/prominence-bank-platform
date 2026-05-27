from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User, OTPToken
from .serializers import LoginSerializer, OTPVerifySerializer, UserSerializer


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email']
        password = serializer.validated_data['password']

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                {'error': 'Invalid credentials'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        if user.is_locked():
            return Response(
                {'error': 'Account is temporarily locked. Try again later.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if not user.check_password(password):
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= 5:
                user.locked_until = timezone.now() + timezone.timedelta(minutes=30)
            user.save()
            return Response(
                {'error': 'Invalid credentials'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        user.failed_login_attempts = 0
        user.locked_until = None
        user.save()

        # Generate OTP
        token, code = OTPToken.generate(user, purpose='login')

        # In development, print OTP to console
        otp_backend = getattr(settings, 'OTP_BACKEND', 'console')
        if otp_backend == 'console':
            print(f"\n{'='*40}")
            print(f"  OTP for {user.email}: {code}")
            print(f"{'='*40}\n")

        return Response({
            'message': 'OTP sent to your email',
            'email': email,
            'otp_required': True,
            # Only surfaced in demo mode (never tie this to DEBUG in a financial API).
            **(({'dev_otp': code} if settings.DEMO_MODE else {})),
        })


class OTPVerifyView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = OTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email']
        otp_code = serializer.validated_data['otp_code']

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                {'error': 'Invalid credentials'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Get latest unused OTP for login
        otp_token = OTPToken.objects.filter(
            user=user,
            purpose='login',
            is_used=False,
            expires_at__gt=timezone.now(),
        ).order_by('-created_at').first()

        if not otp_token or not otp_token.verify(otp_code):
            return Response(
                {'error': 'Invalid or expired OTP'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        refresh['role'] = user.role
        refresh['email'] = user.email
        refresh['full_name'] = user.full_name

        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserSerializer(user).data,
        })


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
        except Exception:
            pass
        return Response({'message': 'Logged out successfully'})


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)
