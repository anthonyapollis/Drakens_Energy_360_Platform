# Kimball bus matrix

> **Independent synthetic portfolio project.** No internal Vivo Energy, Engen, Shell or Vitol data. Every value described here is generated.

Which conformed dimensions each business process uses. Generated from the actual model, so it cannot drift from the tables that exist.

A dimension is marked where the fact table carries its key. The value of the matrix is the columns: `dim_site` appearing across retail, supply, maintenance and safety is what makes it possible to ask one question of all four.

## Retail and forecourt

| Business process | Date | Site | Product | Customer | Supplier | Terminal | Vehicle | Asset | Employee | Contract |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| forecourt shift | x | x |  |  |  |  |  |  |  |  |
| price changes | x | x | x |  |  |  |  |  |  |  |
| promotions | x | x |  |  |  |  |  |  |  |  |
| pump meter readings | x | x | x |  |  |  |  |  |  |  |
| retail fuel payments | x | x |  |  |  |  |  |  |  |  |
| retail fuel sales | x | x | x |  |  |  |  |  |  |  |
| shop returns | x | x | x |  |  |  |  |  |  |  |
| shop sales | x | x | x |  |  |  |  |  |  |  |
| site daily operations | x | x |  |  |  |  |  |  |  |  |
| tank dips | x | x | x |  |  |  |  |  |  |  |

## Commercial and B2B

| Business process | Date | Site | Product | Customer | Supplier | Terminal | Vehicle | Asset | Employee | Contract |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| commercial deliveries | x |  | x | x |  |  | x |  |  |  |
| commercial order lines | x |  | x | x |  |  |  |  |  |  |
| commercial orders | x |  | x | x |  |  |  |  |  | x |
| contract pricing | x |  | x |  |  |  |  |  |  | x |
| contract volume commitments | x |  | x | x |  |  |  |  |  | x |
| customer credit exposure | x |  |  | x |  |  |  |  |  |  |
| customer invoices | x |  |  | x |  |  |  |  |  |  |
| customer receipts | x |  |  | x |  |  |  |  |  |  |
| customer service cases | x |  |  | x |  |  |  |  |  |  |

## Supply and storage

| Business process | Date | Site | Product | Customer | Supplier | Terminal | Vehicle | Asset | Employee | Contract |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| import cargoes | x |  | x |  | x |  |  |  |  |  |
| inventory adjustments | x | x | x |  |  |  |  |  |  |  |
| inventory movements | x | x | x |  |  | x |  |  |  |  |
| inventory snapshot | x | x | x |  |  | x |  |  |  |  |
| procurement orders | x |  | x |  | x | x |  |  |  |  |
| procurement receipts | x |  | x |  | x | x |  |  |  |  |
| replenishment orders | x | x | x |  |  | x |  |  |  |  |
| stock losses | x | x | x |  |  | x |  |  |  |  |
| terminal issues | x |  | x |  |  | x | x |  |  |  |
| terminal receipts | x |  | x |  | x | x |  |  |  |  |
| terminal throughput | x |  | x |  |  | x |  |  |  |  |

## Logistics and fleet

| Business process | Date | Site | Product | Customer | Supplier | Terminal | Vehicle | Asset | Employee | Contract |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| deliveries | x |  | x |  |  |  | x |  |  |  |
| delivery events | x |  |  |  |  |  | x |  |  |  |
| fleet costs | x |  |  |  |  |  | x |  |  |  |
| route performance | x |  |  |  |  |  |  |  |  |  |
| vehicle trips | x |  |  |  |  |  | x |  |  |  |

## LPG

| Business process | Date | Site | Product | Customer | Supplier | Terminal | Vehicle | Asset | Employee | Contract |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| lpg bulk deliveries | x |  |  | x |  |  | x |  |  |  |
| lpg cylinder movements | x | x |  |  |  |  |  |  |  |  |
| lpg inventory snapshot | x | x |  |  |  |  |  |  |  |  |
| lpg sales | x | x | x | x |  |  |  |  |  |  |

## Lubricants

| Business process | Date | Site | Product | Customer | Supplier | Terminal | Vehicle | Asset | Employee | Contract |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| lubricant inventory snapshot | x |  | x |  |  |  |  |  |  |  |
| lubricant orders | x |  | x | x |  |  |  |  |  |  |
| lubricant sales | x | x | x | x |  |  |  |  |  |  |

## Aviation

| Business process | Date | Site | Product | Customer | Supplier | Terminal | Vehicle | Asset | Employee | Contract |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| aircraft uplifts | x |  |  |  |  |  |  |  |  |  |
| aviation inventory snapshot | x |  | x |  |  |  |  |  |  |  |
| aviation sales | x |  | x | x |  |  |  |  |  |  |

## Marine

| Business process | Date | Site | Product | Customer | Supplier | Terminal | Vehicle | Asset | Employee | Contract |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| bunker deliveries | x |  |  |  |  |  |  |  |  |  |
| marine inventory snapshot | x |  | x |  |  |  |  |  |  |  |
| marine sales | x |  | x | x |  |  |  |  |  |  |

## Loyalty and digital

| Business process | Date | Site | Product | Customer | Supplier | Terminal | Vehicle | Asset | Employee | Contract |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| campaign responses | x |  |  |  |  |  |  |  |  |  |
| digital events | x | x |  |  |  |  |  |  |  |  |
| digital sessions | x |  |  |  |  |  |  |  |  |  |
| loyalty points balance | x |  |  |  |  |  |  |  |  |  |
| loyalty transactions | x | x |  |  |  |  |  |  |  |  |
| mobile payments | x | x |  |  |  |  |  |  |  |  |

## New energy

| Business process | Date | Site | Product | Customer | Supplier | Terminal | Vehicle | Asset | Employee | Contract |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| energy costs | x | x |  |  |  |  |  |  |  |  |
| ev charger status | x | x |  |  |  |  |  |  |  |  |
| ev charging sessions | x | x |  |  |  |  |  |  |  |  |
| grid import export | x | x |  |  |  |  |  |  |  |  |
| site energy consumption | x | x |  |  |  |  |  |  |  |  |
| solar generation | x | x |  |  |  |  |  |  |  |  |

## Assets and maintenance

| Business process | Date | Site | Product | Customer | Supplier | Terminal | Vehicle | Asset | Employee | Contract |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| asset downtime | x | x |  |  |  |  |  | x |  |  |
| asset failures | x | x |  |  |  |  |  | x |  |  |
| asset inspections | x | x |  |  |  |  |  | x |  |  |
| asset meter readings | x | x |  |  |  |  |  | x |  |  |
| maintenance work orders | x | x |  |  |  |  |  | x |  |  |
| spare parts usage | x |  |  |  |  |  |  | x |  |  |

## HSSEQ

| Business process | Date | Site | Product | Customer | Supplier | Terminal | Vehicle | Asset | Employee | Contract |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| environmental events | x | x |  |  |  | x |  |  |  |  |
| hsseq incidents | x | x |  |  |  |  |  |  |  |  |
| near misses | x | x |  |  |  |  |  |  |  |  |
| permit to work | x | x |  |  |  |  |  |  |  |  |
| safety observations | x | x |  |  |  |  |  |  |  |  |
| training compliance | x | x |  |  |  |  |  |  | x |  |
| vehicle safety events | x |  |  |  |  |  | x |  |  |  |

## Finance and planning

| Business process | Date | Site | Product | Customer | Supplier | Terminal | Vehicle | Asset | Employee | Contract |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| accounts payable | x |  |  |  | x |  |  |  |  |  |
| accounts receivable | x |  |  | x |  |  |  |  |  |  |
| budget | x |  |  |  |  |  |  |  |  |  |
| budget vs actual | x |  |  |  |  |  |  |  |  |  |
| capex | x | x |  |  |  |  |  |  |  |  |
| cashflow | x |  |  |  |  |  |  |  |  |  |
| daily executive kpi | x | x |  |  |  |  |  |  |  |  |
| finance revenue cost | x | x |  |  |  |  |  |  |  |  |
| forecast | x | x | x |  |  |  |  |  |  |  |
| general ledger | x |  |  |  |  |  |  |  |  |  |
| opex | x | x |  |  |  |  |  |  |  |  |
| working capital | x |  |  |  |  |  |  |  |  |  |

## Dimension reach

How many fact tables each conformed dimension joins. The high-reach dimensions are the ones worth investing in: an error in `dim_site` is wrong in dozens of places at once.

| Dimension | Fact tables |
|---|---:|
| Date | 85 |
| Site | 44 |
| Product | 32 |
| Customer | 15 |
| Terminal | 10 |
| Vehicle | 8 |
| Asset | 6 |
| Supplier | 5 |
| Contract | 3 |
| Employee | 1 |

