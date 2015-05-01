# -*- coding: utf-8 -*-

from django.conf import settings
from rest_framework import serializers
from rest_framework import status
from rest_framework.generics import CreateAPIView, DestroyAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.relations import PrimaryKeyRelatedField, ManyRelatedField
from rest_framework.response import Response

from zds.member.api.permissions import IsStaffUser
from zds.member.api.serializers import ProfileSanctionSerializer
from zds.member.models import Profile


class CreateDestroyMemberSanctionAPIView(CreateAPIView, DestroyAPIView):
    """
    Generic view used by the API about sanctions.
    """

    queryset = Profile.objects.all()
    serializer_class = ProfileSanctionSerializer
    permission_classes = (IsAuthenticated, IsStaffUser)

    def post(self, request, *args, **kwargs):
        return self.process_request(request)

    def delete(self, request, *args, **kwargs):
        return self.process_request(request)

    def process_request(self, request):
        instance = self.get_object()
        serializer = self.serializer_class(instance, data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        state = self.get_state_instance(request)

        ban = state.get_sanction(request.user, instance.user)
        try:
            state.apply_sanction(instance, ban)
        except ValueError:
            return Response({u'detail': u'Sanction could not be applied with received data.'},
                            status=status.HTTP_400_BAD_REQUEST)
        msg = state.get_message_sanction() \
            .format(ban.user,
                    ban.moderator,
                    ban.type,
                    state.get_detail(),
                    ban.text,
                    settings.ZDS_APP['site']['litteral_name'])
        state.notify_member(ban, msg)
        return Response(serializer.data)

    def get_state_instance(self, request):
        raise NotImplementedError('`get_state_instance()` must be implemented.')


class ZdSModelSerializer(serializers.ModelSerializer):
    def get_fields(self):
        fields = super(ZdSModelSerializer, self).get_fields()

        request = self._context.get('request')
        if request is None:
            return fields

        expands = request.GET.getlist('expand')
        if expands:
            fields = self._update_expand_fields(fields, expands)

        format = request.META.get('HTTP_X_DATA_FORMAT') or 'Markdown'
        if hasattr(self.Meta, 'formats'):
            fields = self._update_format_fields(fields, format)

        return fields

    def _update_expand_fields(self, fields, expands):
        assert hasattr(self.Meta, 'serializers'), (
            'Class {serializer_class} missing "Meta.serializers" attribute'.format(
                serializer_class=self.__class__.__name__
            )
        )

        dict_serializers = dict()
        for serializer in self.Meta.serializers:
            dict_serializers[serializer.Meta.model] = serializer

        for expand in expands:
            field = fields.get(expand)
            args = {}
            current_serializer = None

            try:
                if isinstance(field, PrimaryKeyRelatedField):
                    current_serializer = dict_serializers[field.queryset.model]
                elif isinstance(field, ManyRelatedField):
                    current_serializer = dict_serializers[field.child_relation.queryset.model]
                    args = {'many': True}

                assert current_serializer is not None, (
                    'You cannot expand a field without a serializer of the same model.'
                )
            except KeyError:
                continue

            fields[expand] = current_serializer(**args)

        return fields

    def _update_format_fields(self, fields, format='Markdown'):
        assert hasattr(self.Meta, 'formats'), (
            'Class {serializer_class} missing "Meta.formats" attribute'.format(
                serializer_class=self.__class__.__name__
            )
        )

        for current in self.Meta.formats:
            if current != format:
                fields.pop(self.Meta.formats[current])

        return fields
