"""Documentation: what every figure on this dashboard means and how it is worked out.

Written for the people reading the numbers rather than for whoever maintains the
app.
"""

import streamlit as st

import sales_lib as lib

st.markdown("### Documentation")

st.markdown(
    f"""
**Crooked Crow Pickling Co. is a fictional company, and every figure here
is invented.** It makes pickles, pickled vegetables and fermented foods. The data is a demo
database, rebuilt by `make_data.py`.

Everything reads one view, `{lib.source()}`, and every query it issues asks for
rows flagged `is_reportable`. The flag keeps internal transfers, samples and
non-food lines out of the figures, so an analyst querying the view by hand gets
the same answers the dashboard shows.

**This dashboard asks why the numbers moved.** Where a report tells you sales
are up 8%, this one says how much of that was price, how much was volume, how
much was a different mix of products, and which customers and items did it.
"""
)

st.markdown("#### The measure")

st.markdown(
    """
**Invoiced Dollars**, net of line discounts. Trade spend and rebates are not in
this data, so this is not a net-sales figure.

**Cases** are cases shipped, whatever the jar size.

**Average price per case** is always dollars over cases and never follows the
measure toggle, because it can only mean one thing. It moves when the mix of
jar sizes moves, even with no list price changing.
"""
)

st.markdown("#### Periods")

st.markdown(
    f"""
Every page compares one window against one other window, named in full under the
filter bar.

A **week window** of 4, 13, 26 or 52 weeks ends on the last **complete** week.
Weeks end Saturday, and the newest week is nearly always part run: comparing four
days against a full week reads as a collapse that has not happened. Its
comparison window is **{lib.PRIOR_YEAR_DAYS} days earlier**, which is 52 whole
weeks, so a Saturday-ending week always meets a Saturday-ending week.

**Year to date** runs from 1 January to the end of the last complete month, and
compares against the same months of the year before.

A **custom range** is whatever you pick, against the same dates a year earlier.

**Filters and the period follow you between pages.** Pick a customer on the
Customers page and the Products page is already filtered to them.
"""
)

st.markdown("#### The Pulse page, top to bottom")

st.markdown(
    """
**The headlines** are behind the **Show headlines** button on the filter bar,
rather than on the page. They are the page written out in sentences, and they
are described in the next section.

**The six tiles.** The row reads left to right as one sentence: the window's
total, then what it was promised to be, then what it was a year ago, then the
three things that between them explain any gap -- what a case sold for, how
many customers bought, and how many items were invoiced. The first tile carries
no delta of its own, because the two tiles beside it are that delta measured
against the two bases anybody asks about.

**The trend.** The window against the same window a year earlier, drawn by week
for a short window and by month for a long one, with budget dashed across it in
green where there is one. Budget is drawn per bucket rather than as one flat
line: laid flat it would accuse every out-of-season week of missing a plan that
was never set that way.

**Is the business growing?** The chart under it is the only thing on the
dashboard that **ignores the period picker**, using nothing from it but the end
date. Each point is the twelve months ending there, so a rolling year always
contains one of every month and the season cancels out, leaving the direction.
It turns a year after the business does. It is the chart to argue with, not the
one to react to.

**What moved.** Gains in green running right, losses in red running left, for
product classes and for superchains. Not the largest, the ones that changed.

**What it is made of.** Ten slices of the same total -- chains, customers,
representatives, classes, pack sizes, brands, items, groups, organizations, PPGs --
each showing its ten largest by whatever measure is on screen. The slate tick
across each bar is that same slice a year earlier, so a bar that has outrun its
tick has grown. This is the part to act on, and it is ranked by size rather than
by change on purpose: what moved is the section above it.

**Which items were repriced, and which moved on volume.** Two tables, deliberately
shorter than their contents: scroll them. Both rank by the size of the effect
and show both tails, since the items that pushed the total up and the items that
pulled it down are the same question asked twice.

**Does it all add up?** The two bridges, at the foot because they are the most
exact thing on the page and the slowest to read. Everything above is a part of
one of those two staircases.
"""
)

st.markdown("#### The headlines")

st.markdown(
    """
Behind the **Show headlines** button on the filter bar.

**No language model writes this, and nothing about it is generated when you
open the page.** It is arithmetic on the same figures drawn everywhere else on
the page, dropped into fixed sentences by the app's own code. The same data
always produces the same words, and there is no number in it that is not also on
a chart you can click.

What varies is which sentences appear. Each one is left out when its number is
too small to be worth reading, so a quiet quarter gets a short paragraph rather
than a padded one. It is always about dollars, whatever the measure toggle says,
because "how did we do" is a money question.
"""
)

st.markdown("#### Price, volume and mix")

st.markdown(
    """
On **Pulse**, the move from last year's sales to this year's is split into
five bars in the left-hand bridge. The split is done item by item and then added
up.

- **Volume** is the change in total cases, valued at last year's average price
  across everything. What the money would have done selling the same blend of
  things, just more or less of it.
- **Mix** is what selling a different blend did, at last year's prices. Moving
  cases out of gallon club and distributor packs and into retail jars earns more without
  charging anyone a cent more, and volume alone would report that as flat.
- **Price** is this year's cases, revalued by each item's own change in
  realized price. Item by item on purpose: a shift between a cheap item and an
  expensive one is mix, not a price rise.
- **New items** and **items dropped** are sales on items that appear in only one
  of the two windows, which have no pair to compare and so cannot be split.
- **Everything else** is items with sales in both windows but no cases
  in one of them, plus rounding. It is whatever the other bars left over, which
  is what makes the bridge land exactly on the closing figure.

Per item the split needs no mix term: an item's price effect and volume effect
add to its change in dollars exactly. Mix only exists once items are added
together. It is the difference between what the items did and what their total
did.

**Realized price is not list price.** It is dollars over cases for whatever
actually shipped, so it moves when the blend of pack sizes or customers behind an
item moves, with no list price changing at all.
"""
)

st.markdown("#### Clicking through")

st.markdown(
    """
**Every bar chart and every table on this dashboard drills.** Click a bar or a
row and a window opens on that one thing: what it did against the same window a
year earlier, its share of what the chart you clicked was drawing, how it has run
over the window, what it splits into, and what moved inside it. The window closes
with a button through to the **Detail** page, which stops aggregating and shows
the rows.

**What you clicked also filters the dashboard**, from the moment you click it. So
you can drill into a customer and then walk the Products and Customers pages
still looking only at them. The window opens with the two ways back out -- return
to the page you came from with the filter on, or without it -- and the **Detail**
page carries a button back to the page you drilled from.

Every drill in force is an orange chip at the top of every page. Click a chip's
cross to drop that one drill and keep the rest, or click its bar again, which
does the same thing. With more than one chip up, **Clear all** drops the lot.

The price bands, the bridges and the trend lines are not clickable, because
Streamlit cannot report a click on a chart drawn in layers. Where one of those
matters, the table beside it drills instead.
"""
)

st.markdown("#### Accounts that have gone quiet")

st.markdown(
    f"""
On **Customers**. A fixed cutoff such as "no order in eight weeks" flags every
account that buys quarterly and misses every account that used to buy weekly and
has been silent a month. So each account is measured against **its own rhythm**:
the median gap between the weeks it bought in over the last
{lib.QUIET_LOOKBACK_WEEKS // 52} years. An account is called quiet when the
silence has run past **{lib.QUIET_MIN_GAPS} of those gaps**, with a floor of
{lib.QUIET_FLOOR_DAYS} days so a weekly buyer is not flagged for missing one
week.

Accounts with fewer than {lib.QUIET_MIN_WEEKS} buying weeks are left out
entirely: there is no rhythm to measure against a handful of orders. The ranking
is by the account's own trailing-year sales, so the largest silences come first
rather than the longest.

Silence is measured to the **end of the window**, not to today, so a part week
never puts anyone on the list.

This is the one list on the dashboard that is a list of things to do. It is still
a prompt to go and look: a plant shutdown, a contract renewal and a lost account
all look identical from here.
"""
)

st.markdown("#### The price spread")

st.markdown(
    f"""
On **Products**. The same item leaves at different prices for different
customers. The band is the range customers actually paid per case and the
diamond is the item's volume-weighted average.

Customers taking less than **{lib.SPREAD_MATERIAL_SHARE:.0%}** of an item's
cases are left out. One pallet at an odd price is a rounding artifact, a sample or a freight adjustment, not a pricing pattern, and left in it sets the low end of nearly every band. An
item needs at least {lib.SPREAD_MIN_CUSTOMERS} customers to appear at all.

The money column is the cases sold below the item's own average, valued at how
far below they were. **It is a question, not a finding.** Pack, freight terms and
contract age all move a realized price and none of them are in this data.
"""
)

st.markdown("#### Budget")

st.markdown(
    """
Budget is a plan finance produces once a year, at customer by item by month
grain.

It appears on the Pulse **Vs budget** tile, on the dashed line across the Pulse
trend chart, and in the Pulse paragraph, for **week windows and year to date
only**. A week window reads the weekly allocation, which spreads a month evenly
across its days; year to date reads the monthly budget directly. A **custom
range gets no budget at all**. An arbitrary range cuts through both, and a budget
that is right to within a few days is worse than no budget, because nobody can
tell which days it missed.

Budget exists for dollars only, and only for years the plan covers. Where there is none the tile says so and its tooltip says which of those
reasons it is, rather than the tile quietly disappearing.

One case is worth knowing about. A 26 or 52 week window is drawn by month but
budgeted by week, so each budget week is counted into the month its Saturday
falls in. The window's total is exact -- every week is counted once -- but a
month boundary on that dashed line can sit a few days out.
"""
)

st.markdown("#### What is not here")

st.markdown(
    """
- **Net sales**, demand plan and forecast.
- **Cost and margin.** There is no actual cost on the sales lines, so there
  would be nothing to set beside a budgeted one.
- **Anything predictive.** Every number on this dashboard is arithmetic on rows
  that exist. Nothing is modeled, fitted or forecast.
"""
)
