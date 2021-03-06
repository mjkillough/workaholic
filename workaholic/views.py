#!/usr/bin/env python
# encoding: utf-8

from django.conf import settings
from django.contrib import auth
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse
from django import http
from django.shortcuts import redirect, render, resolve_url
from django.utils.http import is_safe_url
from django.views.decorators.http import require_http_methods

from . import models, push, forms, tracker, api
from .json import json_view


@login_required
def index(request):
    recent_periods = models.Period.objects.filter(user=request.user).order_by('-id')[:10]

    api_key = api.get_api_key_for_user(request.user)
    api_start_url = reverse('api-start', args=[api_key])
    api_end_url = reverse('api-end', args=[api_key])

    return render(request, 'main.html', dict(
        has_ongoing_period=tracker.has_ongoing_period(request.user),
        recent_periods=recent_periods,
        api_start_url=api_start_url,
        api_end_url=api_end_url,
    ))


@json_view()
def manifest(request):
    """Serves manifest for being a Progress Web App.

    We serve this dynamically so that we can store GCM_PROJECT_ID
    in one place.
    """
    return dict(
        shortname='Workaholic',
        name='Workaholic',
        gcm_sender_id=settings.GCM_PROJECT_ID,
    )


@require_http_methods(['GET', 'POST'])
def signup(request):
    redirect_field_name = 'next'
    redirect_to = request.POST.get(redirect_field_name,
        request.GET.get(redirect_field_name, '')
    )
    if not is_safe_url(url=redirect_to, host=request.get_host()):
        redirect_to = resolve_url(settings.LOGIN_REDIRECT_URL)
    redirect_response = http.HttpResponseRedirect(redirect_to)

    if request.user.is_authenticated():
        return redirect_response

    form = forms.SignupForm()
    if request.method == 'POST':
        form = forms.SignupForm(request.POST)
        if form.is_valid():
            user = form.save()

            # We must call authenticate(), as login() expects it to set
            # a backend.
            user = auth.authenticate(
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password1']
            )
            auth.login(request, user)
            return redirect_response

    return render(request, 'auth/signup.html', dict(
        form=form,
        next=redirect_to
    ))


@login_required
@json_view(['identifier'])
@require_http_methods(['POST'])
def subscribe(request, identifier):
    try:
        identifier = push.normalize_identifier(identifier)
    except push.BadIdentifierException as e:
        return http.HttpResponseBadRequest, dict(success=False, error=e.msg)
    # Be nice and allow the client app to tell us about the same
    # subscription more than once.
    models.PushSubscription.objects.get_or_create(
        user=request.user, identifier=identifier
    )
    return dict(success=True)


@login_required
@json_view(['identifier'])
@require_http_methods(['POST'])
def unsubscribe(request, identifier):
    try:
        identifier = push.normalize_identifier(identifier)
        models.PushSubscription.objects.get(identifier=identifier).delete()
    except push.BadIdentifierException as e:
        return http.HttpResponseBadRequest, dict(success=False, error=e.msg)
    except models.PushSubscription.DoesNotExist:
        return http.HttpResponseBadRequest, dict(
            success=False, error='Subscription does not exist'
        )
    return dict(success=True)


@login_required
@require_http_methods(['POST'])
def tracker_start(request):
    tracker.start_period(request.user)
    return redirect('index')


@login_required
@require_http_methods(['POST'])
def tracker_end(request):
    tracker.end_ongoing_periods(request.user)
    return redirect('index')


@api.endpoint()
def api_tracker_start(request):
    tracker.start_period(request.user)
    return dict(success=True)


@api.endpoint()
def api_tracker_end(request):
    tracker.end_ongoing_periods(request.user)
    return dict(success=True)
