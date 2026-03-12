from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed
from apps.users.models import User

class MongoJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        user_id = validated_token.get('user_id')
        if not user_id:
            raise AuthenticationFailed('Token contained no recognizable user identification')
        
        user = User.objects(id=user_id).first()
        if not user:
            raise AuthenticationFailed('User not found', code='user_not_found')
            
        return user
