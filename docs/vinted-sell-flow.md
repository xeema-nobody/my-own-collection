# Vinted sell flow (researched 2026-11-11, vinted.nl, English UI, logged-in account)

Read-only walk of `https://www.vinted.nl/items/new` (nothing uploaded, nothing published). Used by roadmap Step 6e (assisted publish: Claude in Chrome fills the form, the user presses Publish; no credentials stored).

## Form fields (order on the page)

| Section | Field | Kind | Notes |
| --- | --- | --- | --- |
| Photos | Upload photos | button / file input | Up to **20 photos** per listing (Vinted Help Centre summary). Not tested live; first photo = cover. |
| About your item | Title | textbox "Tell buyers what you're selling" | 6c limit constant 100 not verified on the form. |
| About your item | Description | textbox "Tell buyers more about it" | 6c limit constant 2000 not verified on the form. |
| Item details | Category | searchable picker | Search "trading card": **Hobbies & collectables > Trading cards > Single trading cards** (others: Trading card lots, Card decks, Uncut card sheets). |
| Item details | Brand | searchable picker | Appears after the category. "Popular brands" list has **Pokémon**, Topps, Panini, Yu-Gi-Oh!. |
| Item details | Condition | picker | Appears after the category. Options: **New with tags, New without tags, Very good, Good, Satisfactory**. |
| Pricing | Price | textbox, placeholder "€0.00" | EUR. |
| Shipping | Parcel size | radio cards | **Small** (large-envelope size, "Recommended" for cards), Medium (shoebox), Large (moving box). Buyer always pays postage. |
| Footer | Save draft / Upload | buttons | "Upload" = publish. The assisted flow must stop before it. |

Dependent fields (Brand, Condition, Shipping) only exist after a category is chosen. Leaving the page with edits triggers a browser "Leave site?" dialog: the fill step must not navigate away mid-fill.

## Decided mapping (user, 2026-11-11)

- Category: **Single trading cards** for raw and graded (decks later use "Card decks").
- Brand: **Pokémon** (other TCGs later).
- Condition: raw -> **Very good**; graded (slab) -> **New without tags**. Editable per item in the confirm table.
- Parcel size: raw -> **Small**, slab -> **Medium**; editable per item.
- Title: card name, number, set, condition or grader + grade (user thinks the limit is ~200; verify on the form, the 6c constant is 100 until then).
- Description: short, natural card description (name, number, set, condition) plus a common service line ("shipping fast and with care").
- Price: EUR, from the per-item confirmation table (suggested price, user can edit).
- Publish: user confirms per item **in our app**; Claude then fills and uploads in the logged-in browser (user decision, amends the earlier "user presses Publish"). Update: the stored Vinted link opens that item's edit page. The item link is read from the Vinted page after publishing and saved on the stack's Vinted listing.

## Form hooks (from the pasted DOM)

Stable `data-testid`s: `add-photos-input` (hidden `input[type=file]`, accepts jpeg/gif/png/webp, multiple), `title--input`, `description--input`, `catalog-select-dropdown-input` (category), `brand-select-dropdown-input`, `category-condition-single-list-input`, `price-input--input`, `1|2|3-package-size--cell` (Small/Medium/Large), `upload-form-save-draft-button`, `upload-form-save-button` (Upload).

## Not verified / fragile

- Photo limit 20 comes from the Help Centre, not from the uploader.
- Title / description character limits (check by typing past the limit).
- Vinted may change labels or pickers; the fill recipe should address fields by visible label, not position.
- Other Vinted domains (.fr, .de) have other UI languages.
