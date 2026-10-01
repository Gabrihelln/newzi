# Briefing Profile

`profile_key` is a deterministic hash of normalized, sorted topics, language, briefing size and country scope. Topic ordering therefore does not affect reuse, while `pt-BR`/`en`, 5/10/15 and `LOCAL`/`GLOBAL`/`BOTH` remain separate profiles.

The first implementation keeps briefing size in the key. A size-15 edition is not sliced to satisfy a size-10 user yet; this avoids silently changing editorial selection and is intentionally documented as a future optimization.

Editorial content is stored once in `BriefingEdition`. `UserBriefingDelivery` stores the user-specific local date, delivery time, timezone and status. Different delivery times can reuse the same edition.
