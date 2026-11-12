# bursa-filing-agent

An agent that reads Bursa Malaysia quarterly reports, pulls out the balance sheet, checks that the
numbers add up (assets = liabilities + equity) before trusting them, and computes financial ratios
in plain Python. Tools are exposed over MCP so any MCP client can use them.

Work in progress: see the issues for the build plan.
