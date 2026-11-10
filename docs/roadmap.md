# Roadmap

What comes after the first public release. Each item will get its own design before code, and its own issue so you can pick it up. Order can change.

## 1. Stocks: B3 and US markets

Today Quilate only knows crypto. The next step adds Brazilian (B3) and US stocks, plus manual purchases for assets that no API reports. The verdict, the rubric and the dashboard need to learn that a stock has no "Monitoring Tag" and no funding rate. Diversification, but make it code.

## 2. MCP server

An MCP (Model Context Protocol) server so an AI assistant can ask Quilate about the portfolio, the verdicts and the analyst's playbook. It would be read-only, like the rest of the system.

## 3. Access code for the local API

The local API has no password today. Another program or another user account on the same Mac can call it. The plan is an access code generated when the server starts, shared with the dashboard and the notch app. See "Known gap" in [threat-model.md](threat-model.md). This is the first public issue.

## 4. Demo mode in the backend

The dashboard has `?demo=1` and the notch app has `notch/demo.sh`. Both use fixed fake data. A demo mode in the backend would run the real cycle on generated data, so you can try the whole system without any account.

## 5. Interface translation

The dashboard, the CLI commands and the notch app are in Portuguese. The plan is to translate them to English, and keep Portuguese.

## 6. Visual identity

A logo, an icon for the notch app and a small design system for Quilate. Right now the logo is the letter Q in a box, which is a bit modest for something named after the purity of gold.
