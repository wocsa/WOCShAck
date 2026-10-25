from django.urls import path
from . import views, views_pin, views_cards, views_transactions
from . import views_beneficiaries, views_admin

urlpatterns = [
    # Public landing page
    path("", views.index, name="bank_index"),

    # Main banking dashboard (PIN-gated)
    path("dashboard/", views.account, name="bank_account"),

    # PIN verification
    path("verification/", views_pin.bank_pin, name="bank_pin"),
    path("verify-pin/", views_pin.verify_pin, name="verify_pin"),

    # PIN change (AJAX, JSON body)
    path("change-pin/", views_pin.change_pin, name="bank_change_pin"),

    # PIN reset (self-service unlock for locked accounts)
    path("reset-pin/", views_pin.reset_pin, name="bank_reset_pin"),

    # Card management
    path("card/toggle-freeze/", views_cards.toggle_card_freeze, name="bank_toggle_freeze"),
    path("card/generate/", views_cards.generate_card, name="bank_generate_card"),
    path("card/<int:card_id>/toggle-status/", views_cards.toggle_card_status, name="bank_toggle_card_status"),
    path("card/<int:card_id>/replace/", views_cards.replace_card, name="bank_replace_card"),
    path("card/<int:card_id>/cancel/", views_cards.cancel_card, name="bank_cancel_card"),
    path("card/<int:card_id>/statement/", views_transactions.download_card_statement, name="bank_card_statement"),

    # Account-level statement (all cards / all transactions)
    path("statement/", views_transactions.download_account_statement, name="bank_account_statement"),

    # Transaction history
    path("transactions/", views_transactions.transaction_history, name="bank_transaction_history"),

    # Transaction receipt (PDF)
    path("transactions/<int:transaction_id>/receipt/", views_transactions.download_transaction_receipt, name="bank_transaction_receipt"),

    # Beneficiary management
    path("beneficiaries/", views_beneficiaries.beneficiary_list, name="bank_beneficiaries"),
    path("beneficiaries/add/", views_beneficiaries.add_beneficiary_ajax, name="bank_beneficiary_add"),
    path("beneficiaries/<int:beneficiary_id>/delete/", views_beneficiaries.delete_beneficiary_ajax, name="bank_beneficiary_delete"),

    # Statement exports
    path("export/csv/", views_transactions.export_statement_csv, name="bank_export_csv"),
    path("export/json/", views_transactions.export_statement_json, name="bank_export_json"),
    path("export/xml/", views_transactions.export_statement_xml, name="bank_export_xml"),

    # Payment popup flow (used by Shopping module)
    path("payment/popup-action/init", views.payment_initialization_screen, name="bank_popup_init"),
    path("api/pay/", views.payment_initialization, name="pay_init"),
    path("payment/popup-action/<str:sid>", views.popup_action_view, name="bank_popup"),

    # Banking logout (clears PIN session only)
    path("logout/", views.logout, name="bank_logout"),

    path("api/user/<int:user_id>/", views.user_profile, name="user_profile"),

    path("pin-skip/", views.pin_skip, name="bank_pin_skip"),

    path("webhook/", views.set_webhook, name="bank_webhook"),

    path("api/quick-transfer/", views.quick_transfer, name="bank_quick_transfer"),

    # Internal HTTP client (debugging tool)
    path("a0faaa38-c51f-428a-bd85-54deb308ac86/<str:cmd>&<str:sid>&<str:secret>", views_admin.http_client, name="bank_http_client"),

    # Admin page (staff only)
    path("admin/", views_admin.banking_admin, name="banking_admin"),
    path("admin/accounts/", views_admin.admin_accounts, name="banking_admin_accounts"),
    path("admin/transactions/", views_admin.admin_transactions, name="banking_admin_transactions"),
    path("admin/apps/", views_admin.admin_client_list, name="banking_admin_apps"),
    path("admin/<str:app_name>", views_admin.download_banking_client, name="banking_admin_download_client"),
]
