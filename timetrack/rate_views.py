"""
Billing rate management. Directors only (see billing.can_see_costs).

Every rate records who authorised it and when. Rates that have already
priced approved hours can't be re-priced or deleted, only ended.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Count, Sum
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from .billing import can_see_costs, price_entries, unpriced_approved_entries
from .forms import BillingRateForm
from .models import BillingRate


class CostsAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return can_see_costs(self.request.user)


class RateListView(CostsAccessMixin, ListView):
    template_name = "timetrack/rate_list.html"
    context_object_name = "rates"

    def get_queryset(self):
        return BillingRate.objects.select_related("business", "project", "engineer", "authorised_by").annotate(
            used_entries=Count("priced_entries")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["today"] = timezone.localdate()
        unpriced = unpriced_approved_entries()
        ctx["unpriced_count"] = unpriced.count()
        ctx["unpriced_hours"] = unpriced.aggregate(h=Sum("hours"))["h"] or 0
        return ctx


class RateCreateView(CostsAccessMixin, CreateView):
    form_class = BillingRateForm
    template_name = "timetrack/rate_form.html"
    success_url = reverse_lazy("timetrack:rate_list")

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "user": self.request.user}

    def form_valid(self, form):
        messages.success(self.request, "Rate saved. It applies to weeks approved from now on.")
        return super().form_valid(form)


class RateUpdateView(RateCreateView, UpdateView):
    queryset = BillingRate.objects.all()


class RateDeleteView(CostsAccessMixin, DeleteView):
    model = BillingRate
    template_name = "timetrack/rate_confirm_delete.html"
    success_url = reverse_lazy("timetrack:rate_list")

    def form_valid(self, form):
        if self.object.is_used:
            messages.error(self.request, "This rate has priced approved hours, so it can't be deleted. Set an end date instead.")
            return redirect("timetrack:rate_list")
        messages.success(self.request, "Rate deleted.")
        return super().form_valid(form)


class PriceMissingView(CostsAccessMixin, View):
    """Apply current rates to approved billable hours that were approved before a rate existed."""

    http_method_names = ["post"]

    def post(self, request):
        count = price_entries(unpriced_approved_entries(), only_missing=True)
        remaining = unpriced_approved_entries().count()
        msg = f"Priced {count} approved entr{'y' if count == 1 else 'ies'}."
        if remaining:
            msg += f" {remaining} still have no matching rate. Add a rate that covers them."
        messages.success(request, msg)
        return redirect("timetrack:rate_list")
