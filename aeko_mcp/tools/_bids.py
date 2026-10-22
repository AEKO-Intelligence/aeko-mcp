"""Bid bounds shared by the ad-group and hosted-workflow tools."""

# The backend's largest max bid in any currency: USD 100 converted to KRW (₩140,000).
# Each ad account is held to its own currency's cap server-side, so a bid above it
# comes back as MARKETING_BID_ABOVE_CAP.
MAX_BID_CEILING_MICROS = 140_000_000_000
