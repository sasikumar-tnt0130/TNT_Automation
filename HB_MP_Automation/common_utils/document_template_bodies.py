"""Professional HTML bodies for Autotest Document Templates.

Modeled on industry self-storage rental agreements (parties, space, rent,
deposit, insurance, access, default, addenda) and HB naming such as
\"Agreement, AZ Rental Agreement HB (lease)\" — unique Autotest wording,
not a verbatim copy of any third-party lease.

Merge Fields are inserted by the UI after this HTML is loaded; labels such
as \"Total Move-In Cost:\" mark where tokens land. Occupant / Tenant Name
is display-only (no merge pill) unless a dedicated tenant-name API token
is in the category token set.
"""
from __future__ import annotations

import re

# Unique Autotest series — distinct from corporate \"AZ Rental Agreement HB\".
SERIES = "HB_MP_Automation"


def _label_lines(*labels: str) -> str:
    """One ``<p><strong>Label:</strong></p>`` per label so tokens do not share a block."""
    return "\n".join(f"<p><strong>{lab}:</strong></p>" for lab in labels)


def _lease_body() -> str:
    return f"""
<h1>{SERIES} — Rental Agreement (Lease)</h1>
<p><em>Unique automation lease for HB_MP_Automation. Structure mirrors
facility rental agreements (e.g. AZ-style HB lease layouts) with Autotest
merge-field anchors for validation.</em></p>

<h2>1. Parties</h2>
<p>This Rental Agreement (&quot;Agreement&quot;) is between the Facility Operator
(&quot;Owner&quot;) and the Occupant identified below (&quot;Occupant&quot;).</p>
<p><strong>Facility / Property Name:</strong></p>
{_label_lines(
    "Facility Address",
    "Occupant / Tenant Name",
    "Lease Signed Date",
)}

<h2>2. Leased Space</h2>
<p>Owner leases to Occupant the storage space identified at move-in
(&quot;Space&quot;), accepted as-is. Approximate size and Space number appear on
the Account Summary and in Hummingbird tenant Documents as
<em>Leased Space No.</em></p>
<p><strong>Space / Unit reference:</strong> (resolved at generation)</p>

<h2>3. Term</h2>
<p>Unless otherwise stated, this Agreement is month-to-month beginning on
the Move-In Date and continues until terminated under Owner's policies
or applicable law. Minimum rental period is one full month unless Owner
publishes a different schedule.</p>

<h2>4. Rent, Deposit, and Move-In Charges</h2>
<p>Occupant shall pay rent and all disclosed fees in advance without
demand. Move-in amounts include rent (prorated when applicable),
security deposit, administrative fees, coverage premiums when enrolled,
and taxes.</p>
{_label_lines(
    "Security Deposit",
    "Insurance / Protection Premium",
    "Total Cost To Move-In / Total Move-In Cost",
)}
<p>Late, NSF, and lien fees apply per posted fee schedule. Owner may
change rates with notice as required by law.</p>

<h2>5. Use of Space</h2>
<p>Space is for storage of personal or business property only. Occupant
shall not reside in the Space, conduct retail sales from the Space, or
store explosives, hazardous materials, perishable food that creates a
nuisance, illegal goods, or property of others without Owner consent.
No subletting without written consent.</p>

<h2>6. Access and Locks</h2>
<p>Occupant provides their own lock unless Owner supplies one under a
separate program. Owner may limit access hours, require gate codes, and
deny access when Occupant is in default. Occupant shall not disable
alarms or share gate credentials in violation of facility rules.</p>

<h2>7. Insurance and Risk of Loss</h2>
<p>Owner does not insure Occupant's property. Occupant must maintain
insurance or enroll in an offered protection plan, or Occupant
self-insures and releases Owner from loss that insurance would cover,
to the extent permitted by law.</p>
{_label_lines(
    "Tenant Insurance Name / Plan",
    "Tenant Insurance Premium",
)}

<h2>8. Default, Lien, and Sale</h2>
<p>Failure to pay rent or fees when due is default. Owner may deny
access, overlock the Space, and enforce statutory storage liens,
including notice and sale of stored property, as allowed by the state
where the Facility is located.</p>

<h2>9. Termination and Move-Out</h2>
<p>Occupant must give notice per facility policy, remove all property,
and return the Space broom-clean. Owner may charge cleaning or disposal
fees for abandoned property.</p>

<h2>10. Entire Agreement</h2>
<p>This Agreement, facility rules, and any signed addenda (military,
vehicle, autopay, coverage, authorized access) form the entire
agreement. Occupant's electronic or clickwrap signature is binding.</p>

<p><strong>Autotest marker:</strong> HB_MP_AUTOTEST_LEASE_V2_AZSTYLE</p>
""".strip()


def _military_body() -> str:
    return f"""
<h1>{SERIES} — Military Service Addendum</h1>
<p>This Addendum supplements the Rental Agreement for Occupants who
disclose active duty, reserve, or dependent military status (including
Servicemembers Civil Relief Act considerations where applicable).</p>

<h2>1. Occupant and Facility</h2>
{_label_lines(
    "Occupant / Tenant Name",
    "Facility Address",
    "Lease Signed Date",
)}

<h2>2. Military Disclosure</h2>
{_label_lines(
    "Servicemember Name",
    "Military Branch Name",
)}
<p>Occupant represents that military status information provided at
rental (branch, identification number, unit, ETS, and commanding
officer contacts when collected) is accurate. Occupant shall notify
Owner within a reasonable time of changes in duty status that affect
this Agreement.</p>

<h2>3. Owner Reliance</h2>
<p>Owner relies on this disclosure to apply statutory protections and
facility policies for service members. Misrepresentation may void
benefits that depend on accurate status.</p>

<h2>4. Acknowledgement</h2>
<p>Occupant acknowledges receipt of this Military Service Addendum and
agrees it is part of the Rental Agreement. File name on tenant
Documents: <em>Military Waiver</em>.</p>

<p><strong>Autotest marker:</strong> HB_MP_AUTOTEST_MILITARY_V3</p>
""".strip()


def _vehicle_body() -> str:
    return f"""
<h1>{SERIES} — Vehicle / Titled Property Addendum</h1>
<p>This Addendum applies when Occupant stores a motor vehicle, trailer,
RV, boat, or other titled property in or associated with the Space
(including parking spaces).</p>

<h2>1. Parties and Space</h2>
{_label_lines(
    "Occupant / Tenant Name",
    "Facility Address",
    "Lease Signed Date",
)}

<h2>2. Vehicle Description</h2>
{_label_lines(
    "Vehicle Make",
    "Vehicle Model",
    "Vehicle License Plate Number",
    "Vehicle VIN",
)}
<p>Occupant shall keep current the vehicle type, year, make, model,
color, license plate, state of registration, and VIN (or hull ID) as
collected on the rental form. Stored vehicles must be operable unless
Owner expressly allows otherwise in writing.</p>

<h2>3. Insurance and Registration</h2>
<p>Occupant shall maintain required liability and physical-damage
coverage and current registration. Owner is not responsible for theft,
vandalism, weather, or mechanical failure of the vehicle.</p>

<h2>4. Towing and Removal</h2>
<p>If Occupant defaults, abandons the vehicle, or violates facility
rules, Owner may tow or remove the vehicle at Occupant's expense under
applicable law and posted policies.</p>

<h2>5. Acknowledgement</h2>
<p>Occupant agrees this Vehicle Addendum is part of the Rental
Agreement. Tenant Documents file name: <em>Vehicle Addendum</em>.</p>

<p><strong>Autotest marker:</strong> HB_MP_AUTOTEST_VEHICLE_V3</p>
""".strip()


def _autopay_body() -> str:
    return f"""
<h1>{SERIES} — Autopay Enrollment Authorization</h1>
<p>Occupant authorizes Owner (and its payment processor) to charge the
payment method on file for recurring rent, fees, and balances due under
the Rental Agreement.</p>

<h2>1. Occupant and Facility</h2>
{_label_lines(
    "Occupant / Tenant Name",
    "Facility Address",
    "Lease Signed Date",
)}

<h2>2. Bank / ACH details on file</h2>
<p>When Autopay uses ACH / E-Check, the following account details apply.</p>
{_label_lines(
    "Routing Number",
    "Bank Account Number",
    "Account Type (Checking / Savings)",
    "Bank City",
    "Bank State",
    "Bank Postal Code",
)}

<h2>3. Authorization</h2>
<p>While Autopay is enabled, Owner may initiate charges on or after each
due date for rent and disclosed fees. Occupant is responsible for
keeping card or ACH details current. Failed payments may incur NSF or
late fees and may result in default.</p>

<h2>4. Cancellation</h2>
<p>Occupant may cancel Autopay by notice to Owner per facility policy;
cancellation does not waive amounts already due.</p>

<h2>5. Acknowledgement</h2>
<p>Occupant acknowledges this Autopay Enrollment Document and agrees
electronic authorization is valid. Tenant Documents file name:
<em>Autopay Enrollment Document</em>.</p>

<p><strong>Autotest marker:</strong> HB_MP_AUTOTEST_AUTOPAY_V3</p>
""".strip()


def _ach_body(category: str = "ACH") -> str:
    """ACH / Auto Debit enrollment body with bank merge-field anchors."""
    safe = category.replace("&", "&amp;")
    marker = "HB_MP_AUTOTEST_" + re.sub(r"[^\w]+", "_", category).upper()[:40]
    return f"""
<h1>{SERIES} — {safe} Authorization</h1>
<p>Occupant authorizes electronic ACH / E-Check debits for rent, fees,
and balances due under the Rental Agreement.</p>

<h2>1. Occupant and Facility</h2>
{_label_lines(
    "Occupant / Tenant Name",
    "Facility Address",
    "Lease Signed Date",
)}

<h2>2. Bank account</h2>
{_label_lines(
    "Routing Number",
    "Bank Account Number",
    "Account Type (Checking / Savings)",
    "Bank City",
    "Bank State",
    "Bank Postal Code",
)}

<h2>3. Authorization</h2>
<p>Occupant authorizes Owner and its payment processor to initiate ACH
debits using the Routing Number and Bank Account Number above. Occupant
confirms the Account Type and bank address details are accurate.</p>

<h2>4. Acknowledgement</h2>
<p>Occupant's signature confirms this <strong>{safe}</strong> authorization
and that electronic debit is valid. It may appear under Hummingbird tenant
Documents with the File Name configured for this category.</p>

<p><strong>Autotest marker:</strong> {marker}</p>
""".strip()


def _drivers_license_body() -> str:
    return f"""
<h1>{SERIES} — Driver License Acknowledgement</h1>
<p>Occupant provides driver license identification for the rental file.</p>

<h2>1. Occupant and Facility</h2>
{_label_lines(
    "Occupant / Tenant Name",
    "Facility Address",
    "Lease Signed Date",
)}

<h2>2. Driver license</h2>
{_label_lines(
    "Driver License Number",
    "Driver License State",
    "Driver License Expiration Date",
)}

<h2>3. Acknowledgement</h2>
<p>Occupant affirms the license details are current and may be used for
identity verification under facility policy.</p>

<p><strong>Autotest marker:</strong> HB_MP_AUTOTEST_DRIVERS_LICENSE_V1</p>
""".strip()


def _insurance_certificate_body() -> str:
    return f"""
<h1>{SERIES} — Insurance Certificate</h1>
<p>Occupant provides proof of personal insurance covering stored property.</p>

<h2>1. Occupant and Facility</h2>
{_label_lines(
    "Occupant / Tenant Name",
    "Facility Address",
    "Lease Signed Date",
)}

<h2>2. Policy</h2>
{_label_lines(
    "Protection / Insurance Name",
    "Insurance Policy Number",
    "Insurance Expiration Date",
    "Insurance / Protection Premium",
)}

<h2>3. Acknowledgement</h2>
<p>Occupant affirms the certificate / policy details are accurate and
will provide updates before expiration when required by Owner.</p>

<p><strong>Autotest marker:</strong> HB_MP_AUTOTEST_INSURANCE_CERT_V1</p>
""".strip()


def _coa_body() -> str:
    return f"""
<h1>{SERIES} — Change of Address Notice (Old and New)</h1>
<p>This notice records a change to Occupant's primary mailing address
for notices under the Rental Agreement.</p>

<h2>1. Occupant</h2>
{_label_lines("Occupant / Tenant Name")}
<p><strong>Space reference:</strong> (resolved at generation)</p>

<h2>2. Addresses</h2>
{_label_lines(
    "Previous / Old Address",
    "New Address — Line 1",
    "New Address — Line 2",
)}

<h2>3. Effect</h2>
<p>Owner may send legal and billing notices to the New Address after
this notice is signed. Occupant remains responsible for updating
contact information if it changes again.</p>

<p><strong>Autotest marker:</strong> HB_MP_AUTOTEST_COA_V2</p>
""".strip()


def _enroll_coverage_body() -> str:
    return f"""
<h1>{SERIES} — Coverage / Protection Plan Enrollment</h1>
<p>Occupant elects to enroll in the facility protection or coverage
plan offered at move-in (or later) in lieu of or in addition to
personal insurance, as disclosed on the rental form.</p>

<h2>1. Occupant and Plan</h2>
{_label_lines(
    "Occupant / Tenant Name",
    "Protection / Insurance Name",
    "Premium",
    "Protected Property description",
)}

<h2>2. Consent</h2>
<p>Occupant consents to the plan terms, premium billing with rent, and
coverage limits stated in the plan brochure or enrollment screen.</p>
{_label_lines("Protection Plan Consent")}

<h2>3. Acknowledgement</h2>
<p>Enrollment does not make Owner an insurer of last resort beyond the
plan terms. Tenant Documents may list coverage under enroll or related
&quot;other&quot; document types depending on property configuration.</p>

<p><strong>Autotest marker:</strong> HB_MP_AUTOTEST_ENROLL_COVERAGE_V2</p>
""".strip()


def _deny_coverage_body() -> str:
    return f"""
<h1>{SERIES} — Coverage Decline / Self-Insurance Acknowledgement</h1>
<p>Occupant declines the facility protection plan and acknowledges that
Owner does not insure Occupant's stored property.</p>

<h2>1. Occupant</h2>
{_label_lines(
    "Occupant / Tenant Name",
    "Facility Address",
    "Lease Signed Date",
)}

<h2>2. Decline</h2>
<p>Occupant declines enrollment and accepts full risk of loss for stored
property except to the extent Occupant maintains separate insurance.
Occupant will not look to Owner's policies for Occupant's contents.</p>

<p><strong>Autotest marker:</strong> HB_MP_AUTOTEST_DENY_COVERAGE_V2</p>
""".strip()


def _authorized_access_body() -> str:
    return f"""
<h1>{SERIES} — Authorized Access Addendum</h1>
<p>Occupant designates person(s) authorized to access the Space and
conduct limited business with Owner regarding the Space.</p>

<h2>1. Occupant and Facility</h2>
{_label_lines(
    "Occupant / Tenant Name",
    "Facility Address",
    "Lease Signed Date",
)}

<h2>2. Authorized Person</h2>
{_label_lines(
    "Authorized Access Person Name",
    "Authorized Access Person Phone",
)}
<p>Authorized persons may enter the Space using Occupant's gate
credentials when permitted by Owner. Occupant remains liable for their
acts.</p>

<h2>3. Revocation</h2>
<p>Occupant may revoke authorization by written notice to Owner.
Owner may refuse access to any person for safety or policy reasons.</p>

<p><strong>Autotest marker:</strong> HB_MP_AUTOTEST_AUTH_ACCESS_V3</p>
""".strip()


def _other_signed_body() -> str:
    return f"""
<h1>{SERIES} — Supplemental Signed Acknowledgement (Other)</h1>
<p>This supplemental document captures signed acknowledgements that
properties classify as <em>Other (With Signature)</em>.</p>

<h2>1. Occupant and Facility</h2>
{_label_lines(
    "Occupant / Tenant Name",
    "Facility Address",
    "Lease Signed Date",
)}

<h2>2. Acknowledgement</h2>
<p>Occupant acknowledges the disclosures presented at rental or in
Account and agrees this signed copy may appear under tenant Documents
with an &quot;other&quot; type file name configured for the property.</p>

<p><strong>Autotest marker:</strong> HB_MP_AUTOTEST_OTHER_SIGNED_V3</p>
""".strip()


def _merge_catalog_body() -> str:
    return f"""
<h1>{SERIES} — Merge Field Validation Catalog</h1>
<p>Welcome-letter style template used only to verify Merge Fields insert
and resolve. Not a customer-facing lease.</p>
{_label_lines(
    "Facility Address",
    "Property Address Line 2",
    "Security Deposit",
    "Insurance / Protection Premium",
    "Tenant Insurance Name / Plan",
    "Total Move-In Cost",
    "Lease Signed Date",
    "Protected Property description",
    "Protection Plan Consent",
    "Notice Delivery Method",
    "Routing Number",
    "Bank Account Number",
    "Account Type (Checking / Savings)",
    "Driver License Number",
    "Insurance Policy Number",
    "Vehicle License Plate Number",
    "Military Branch Name",
)}
<p><strong>Autotest marker:</strong> HB_MP_AUTOTEST_MERGE_CATALOG_V4</p>
""".strip()


def _key_deposit_body() -> str:
    return f"""
<h1>{SERIES} — Key Deposit Agreement</h1>
<p>Occupant acknowledges a refundable key / access-device deposit held
by Owner under the Rental Agreement.</p>

<h2>1. Occupant and Facility</h2>
{_label_lines(
    "Occupant / Tenant Name",
    "Facility Address",
    "Lease Signed Date",
)}

<h2>2. Deposit</h2>
{_label_lines("Security Deposit")}
<p>The deposit is refundable subject to return of all keys/devices and
payment of outstanding balances at move-out.</p>

<p><strong>Autotest marker:</strong> HB_MP_AUTOTEST_KEY_DEPOSIT_V1</p>
""".strip()


def _party_category_body(category: str) -> str:
    """Acknowledgement / waiver body — party + facility only (no charges)."""
    safe = category.replace("&", "&amp;")
    marker = "HB_MP_AUTOTEST_" + re.sub(r"[^\w]+", "_", category).upper()[:40]
    return f"""
<h1>{SERIES} — {safe}</h1>
<p><em>Unique Autotest acknowledgement for Template Category
<strong>{safe}</strong>.</em></p>

<h2>1. Parties and Facility</h2>
{_label_lines(
    "Occupant / Tenant Name",
    "Facility Address",
    "Lease Signed Date",
)}

<h2>2. Purpose — {safe}</h2>
<p>Occupant acknowledges the terms that apply to the <strong>{safe}</strong>
category under the Rental Agreement and facility rules.</p>

<h2>3. Acknowledgement</h2>
<p>Occupant's signature confirms receipt of this <strong>{safe}</strong>
document. It may appear under Hummingbird tenant Documents with the File
Name configured for this category on the property.</p>

<p><strong>Autotest marker:</strong> {marker}</p>
""".strip()


def _charge_category_body(category: str) -> str:
    """Charge / fee body — party + deposit / premium / move-in cost only."""
    safe = category.replace("&", "&amp;")
    marker = "HB_MP_AUTOTEST_" + re.sub(r"[^\w]+", "_", category).upper()[:40]
    return f"""
<h1>{SERIES} — {safe}</h1>
<p><em>Unique Autotest charge document for Template Category
<strong>{safe}</strong>.</em></p>

<h2>1. Parties and Facility</h2>
{_label_lines(
    "Occupant / Tenant Name",
    "Facility Address",
    "Lease Signed Date",
)}

<h2>2. Charges</h2>
{_label_lines(
    "Security Deposit",
    "Insurance / Protection Premium",
    "Total Move-In Cost",
)}

<h2>3. Acknowledgement</h2>
<p>Occupant acknowledges the charges disclosed for
<strong>{safe}</strong> under the Rental Agreement.</p>

<p><strong>Autotest marker:</strong> {marker}</p>
""".strip()


def _generic_category_body(category: str) -> str:
    """Fallback body — party-only so unrelated charge/bank fields are not dumped."""
    return _party_category_body(category)


def _superlease_style_body() -> str:
    return f"""
<h1>{SERIES} — Superlease-Style Cost Card Agreement</h1>
<p><em>Note: Live tenant File Name &quot;Superlease&quot; is normally produced by
the Super Lease engine under Lease Configuration. This Autotest
template (Type Lease) supports merge-field and layout checks when
assigned; it does not replace the Super Lease product engine.</em></p>

<h2>1. Space Card Summary</h2>
{_label_lines(
    "Occupant / Tenant Name",
    "Facility Address",
    "Total Move-In Cost",
    "Security Deposit",
    "Insurance Premium",
)}

<h2>2. Payment Cycle and Coverage</h2>
<p>Payment cycle, coverage selection, and contact blocks (alternate,
emergency, authorized access) appear when collected on the rental form,
consistent with Superlease content validations in the automation suite.</p>

<p><strong>Autotest marker:</strong> HB_MP_AUTOTEST_SUPERLEASE_STYLE_V2</p>
""".strip()


# Keyword → specialist body (first match wins; case-insensitive).
# Prefer exact / whole-word style matches so "Release" does not hit "lease".
_SPECIALIST_MATCHERS: list[tuple[tuple[str, ...], object]] = [
    (("super lease", "superlease"), _superlease_style_body),
    (("military",), _military_body),
    (("vehicle", "valet", "parking", "no tag"), _vehicle_body),
    (("autopay",), _autopay_body),
    (("auto debit",), lambda: _ach_body("Auto Debit Enrollment Form")),
    (("drivers license", "driver license", "driver's license"), _drivers_license_body),
    (("insurance certificate",), _insurance_certificate_body),
    (("key deposit",), _key_deposit_body),
    (("change of address",), _coa_body),
    (("enroll coverage", "coverage enrollment"), _enroll_coverage_body),
    (("deny coverage", "coverage decline"), _deny_coverage_body),
    (("authorized access",), _authorized_access_body),
    (("welcome letter", "merge field catalog", "catalog"), _merge_catalog_body),
    (("other (", "other)"), _other_signed_body),
]

_CHARGE_BODY_NEEDLES = (
    "wine",
    "discount",
    "rent change",
    "delinquency",
    "lien",
)


def html_for_category(category: str) -> str:
    """Return the best professional HTML body for a live Template Category.

    Bodies include only labels that match that category's related merge
    tokens — no unrelated charge/bank/license dumps.
    """
    key = (category or "").strip().lower()
    if key == "lease" or key.startswith("lease ") or key.endswith(" lease"):
        return _lease_body()
    if key == "other" or key.startswith("other"):
        return _other_signed_body()
    # Exact ACH (do not match "Authorization…")
    if key == "ach" or key.startswith("ach ") or key.endswith(" ach"):
        return _ach_body("ACH")
    if "welcome card" in key:
        return _party_category_body(category)
    for needles, factory in _SPECIALIST_MATCHERS:
        if any(n in key for n in needles):
            return factory()  # type: ignore[operator]
    if any(n in key for n in _CHARGE_BODY_NEEDLES):
        return _charge_category_body(category)
    return _generic_category_body(category)
