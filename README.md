## Overview
This project analyzes housing affordability stress across Ottawa wards by combining:
- Ward-level average household income
- Ward-level market indicators (e.g., median listing price, listing volume) derived from real estate listings 

**The core metric is**
*Price-to-Income Ratio = Median Home Price ÷ Average Household Income*

**Project Objective**
The goal of this project is to identify and compare home affordability stress among Ottawa wards by looking into:
- Household Income Capacity
- Market housing costs
- Signs of market pressure

This methodology emphasizes interpretability and policy relevance using straightforward formulas and dashboard visuals.

## Sheet 1: Housing Stress Ranking (Price-to-Income Ratio) 

This ranks wards by a transparent affordability proxy:</p>
<p align="center"> <img src="tableau\Sheet1.png"" alt="Sheet 1w" width="600"> </p>

<b>*Price-to-Income Ratio = Median Home Price ÷ Average Household Income*</b>

Higher ratios indicate that housing costs are large relative to typical household earnings in that ward.

## Sheet 2: Wages vs Housing (Dual-Axis: Income vs Median Price)

This sheet shows whether expensive housing prices relate to high incomes, or whether prices are not related to local earnings which is a key affordability stress signal.
<p align="center"> <img src="tableau\Sheet2.png"" alt="Sheet 2" width="600"> </p>

- Mismatch risk: Wards where price rises much faster than income indicate stronger affordability pressure than wards where both move together.
- Policy relevance: This supports targeted affordability programs, supply-side actions, or zoning reviews in wards where the gap is most extreme.

## Sheet 3: Market Intensity vs Stress

This sheet provides a “pressure test” of affordability stress by checking how it relates to market activity.

<img src="tableau\Sheet3.png" alt="Sheet 3 - Market Intensity vs Stress" width="900"> 

<ul>
  <li><b>High stress + high activity:</b> suggests market churn where affordability remains strained (possible demand hotspots).</li>
  <li><b>High stress + low activity:</b> suggests affordability pressure without strong market volume (possible constrained supply or pricing stickiness).</li>
  <li><b>Walk Score angle (if used):</b> If high-stress wards also show high walkability, this may indicate amenity-driven pricing pressure.</li>
</ul>

## Summary Interpretation
<img src="tableau/Dashboard 1.png" alt="Dashboard" width="900">
Overall, the dashboard highlights wards where housing costs appear high relative to typical household earnings, that can be interpreted as elevated affordability stress.
<ul>
  <li><b>Primary risk indicator:</b> Price-to-Income Ratio (stress ranking)</li>
  <li><b>Structural signal:</b> Income vs Price divergence (dual-axis gap)</li>
  <li><b>Market dynamics:</b> Activity vs stress (scatter patterns)</li>
</ul>

**Limitations**

This is based on listing-derived median prices and does not reflect the total housing prices.

- Price-to-income is a proxy indicator; it does not directly reflect monthly housing costs (e.g., rent/mortgage payments).

-Ward-level averages might not be shown within- ward variance and inequity.
