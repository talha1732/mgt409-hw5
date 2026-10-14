#Problem 1: Vibe coder prompts
Prompt:
each prompt I write, you need to save that in ai_prompts.md just like in hw 2 and 3 folder. you can check the structure there.

2nd Prompt: Not needed

#Problem 2: Study the Campus Customs database
Prompt:
Can you check the data/campus_customs.db file and look at all the tables and their fields.
Make a copy of the original database as data/campus_customs_new.db because we will be using this copy for the next problems. Don't change the original file.
Also check the 3 open tickets and see how they are linked to the other tables.
Create a file output/harness.md and list all the tables, their fields and one short line explaining why each table is useful for the agents.
In the end, check that both files are created properly.

2nd Prompt: Not needed

#Problem 3: Build the MCP server
Prompt:
Can you create a MCP server using FastMCP inside the mcp_server folder.
It should use data/campus_customs_new.db as the database.
Create 3 MCP tools that will help us with the open tickets 101, 102 and 103.
Check the database and tickets first to see what information each tool needs. Make sure the tools have clear names and only use the data available in the database. Don't make up any data.
Also update output/harness.md and add the following for each tool:
- Tool name
- Which table it reads
- Which ticket it helps (101, 102 or 103)
- One short line explaining why this tool is useful for that ticket
Create a README.md file inside mcp_server folder that explains what the MCP server does, which database it uses and the 3 tools we created.
We don't need to connect or run the MCP server for now.
In the end, check that all the files are created properly.

2nd Prompt: It built and tested the server but left installing fastmcp to me, so I told it "do everything on your own"

#Problem 4: Add MCP Server to Vibe Coder and Test Tools
Prompt:
Can you connect the MCP server we created in Problem 3 to this project so that you can use its tools.
Create a .mcp.json file in the project root with the connection details for the MCP server.
Once connected, test all 3 MCP tools we created in the previous problem.
Save the results in output/mcp_smoke.json
For each tool include the following:
- The prompt used to test the tool
- Tool name
- Tool output
Make sure the output matches the actual information in data/campus_customs_new.db and don't make up any data.
In the end, check that all 3 tools are working properly and the results are saved in the correct format.

2nd Prompt: Not needed

#Problem 5: Build the Agent Team and Grow MCP Tools
Prompt:
Can you build a multi agent system for Campus Customs using PydanticAI.
We need 5 agents:
- Boss
- Inventory
- Accounting
- Facilities
- Customer Service
Create the agents inside backend/ folder and keep one prompt file for each agent in backend/prompts/.
Create backend/models.py for the data models and set up agent loops so the agents can communicate with each other and delegate tasks when needed.
Each agent should have a detailed prompt explaining its role, responsibilities, what it can do and what it should not do. The Boss agent should be able to coordinate the other agents.
Also check the 3 open tickets 101, 102 and 103 and add any additional MCP tools needed to handle them.
Make sure all agents use the MCP server to get information from data/campus_customs_new.db. Don't create another way for agents to access the database and don't make up any information.
Create output/audit_trail.json to record what the agents are doing. It should track each step in the agent loop so we can check it later. Make sure new records are appended and previous records are not deleted.
Update output/harness.md with the following:
- All 5 agents and their responsibilities
- All MCP tools and which tables they use
- Safety rules for agents when dealing with customers and money
- How token usage will be controlled to avoid unnecessary costs
Also update mcp_server/README.md with all the MCP tools including the new ones.
In the end, check that the agents, MCP tools and files are set up correctly.

2nd Prompt: Not needed

#Problem 6: Plan the Three Tickets
Prompt:
Can you create a one page HTML file output/desk_tickets.html where we can see the plan for all 3 open tickets 101, 102 and 103.
The page should have 3 tabs, one for each ticket, so we can switch between them without opening another page.
Check the tickets and the database first to understand what each ticket needs.
For each ticket, create an Expected section that includes the following:
- What the ticket is about
- Which agent the Boss should call first and why
- All the other agents that might need to be involved and what tasks they will handle
- Which MCP tools the agents will use to get the required information
- The expected steps the agents will follow to resolve the ticket
- What the final outcome should look like
Make sure the Boss only calls the agents that are required for each ticket instead of calling all 5 agents unnecessarily.
Also add an Actual section for each ticket but leave it empty for now because we will fill it after running the agents.
Add 2 more tabs for Cash and Reflection. We will work on these in the later problems, so leave them empty or add a coming later message.
Use the actual ticket information from data/campus_customs_new.db and the MCP tools we created in the previous problems. Don't make up any data.
Make the HTML page clean and easy to navigate.
In the end, check that the file is created properly and all the tabs are working.

2nd Prompt: Not needed

#Problem 7: Backend Routes
Prompt:
Can you create the backend API using FastAPI inside backend/main.py so that our frontend dashboard can communicate with the agents and database.
We need the following API routes:
- Get all 3 tickets 101, 102 and 103 along with their current status (open or resolved)
- Run the agent team for a specific ticket using its ticket ID
- Get recent agent events including which agents were involved, what they said and which MCP tools they used
- Approve a payment or purchase after a human confirms it. Agents should only prepare the payment and not change cash themselves
- Get the current checking account balance from the cash_accounts table
- Reset data/campus_customs_new.db to its original values so we can test everything again
Make sure the routes work with the agents and MCP server we created in the previous problems.
Use the existing database and don't create another way for agents to access shop information. The cash balance should only change when a payment is approved.
Also make sure the agent events are recorded in output/audit_trail.json so the frontend can display them.
Update output/harness.md and add all the API routes with one short line explaining what each route does.
Use the following command from backend/ to start the server:
uvicorn main:app --reload --port 8000
The backend should run on http://localhost:8000
In the end, run the backend and test all the API routes to make sure they are working properly. Don't approve any real payment while testing.

2nd Prompt: Not needed

#Problem 8: Agent Dashboard
Prompt:
Can you build a frontend dashboard for Campus Customs using React + Vite + TypeScript inside frontend/ folder.
The dashboard should use the backend API we created in Problem 7.
It should have the following features:
- Show all 3 tickets 101, 102 and 103 with their current status
- Allow me to select a ticket and run the agent team on it
- Show all the agents and what they are doing or saying while working on the ticket
- Show which MCP tools each agent is using
- Mark a ticket as resolved once the agents finish their work
- Show a short summary of what each agent did for that ticket
- Allow a human to approve payments or purchases when required. Agents should not be able to approve payments themselves
- Show the current checking account balance and update it after a payment is approved
Make sure the frontend communicates with the backend at http://localhost:8000.
Also update the backend CORS settings to allow requests from http://localhost:5173.
For the dashboard design, make it look like a modern operations management system. It should have a clean layout, good colors, ticket cards, agent activity section and clear status indicators.
Make sure it is easy to understand which agents are working, which tickets are completed and whether any payment needs approval.
Create output/design.md and explain the following:
- Why you chose this dashboard layout
- How the different agents are shown
- How resolved tickets and payment approvals are displayed
- What design choices make the dashboard easy to use
Use the following command from frontend/ to start the dashboard:
npm run dev
In the end, run the frontend and check that it connects properly with the backend. Test the ticket selection, agent activity, summaries and payment approval flow to make sure everything works.

2nd Prompt: Not needed

#Problem 9: Resolve the Tickets
Prompt:
Can you run the agent team we created in the previous problems and resolve all 3 tickets 101, 102 and 103 using the dashboard.
Before starting, reset data/campus_customs_new.db to its original values so we can start fresh.
Also check the starting checking account balance from the cash_accounts table and save it so we can compare it later.
Run all 3 tickets using the agent team until they are resolved. Make sure the Boss delegates tasks to the correct agents and all agents use the MCP tools to get information from the database.
Once the tickets are resolved, update output/desk_tickets.html.
For each ticket, fill the Actual section with the following:
- Which agents worked on the ticket
- Which tasks the Boss delegated to each agent
- Which MCP tools were used
- What each agent did to resolve the ticket
- The final outcome of the ticket
Keep the Expected section unchanged so we can compare what we planned with what actually happened.
Also update the Cash tab in output/desk_tickets.html with the following:
- Starting checking account balance
- How much cash changed for each ticket and why
- Which payment or purchase was made and its amount
- Ending checking account balance
Make sure payments and purchases are only processed after human approval. The ending balance should match the actual cash_accounts table in the database. Don't make up any amounts.
Create output/resolved_tickets.json with the following for each ticket:
- Ticket ID
- Final status
- Short summary of how it was resolved
- Which agents contributed and what they did
- Any human approvals required
Also create output/resolved_board.html that shows screenshots of the React dashboard after each ticket is resolved. There should be one screenshot for each ticket 101, 102 and 103.
Make sure all agent activities are appended to output/audit_trail.json and previous records are not deleted.
Finally, update output/harness.md so it includes all the database tables, MCP tools, 5 agents, API routes, dashboard details and safety rules.
In the end, check that all 3 tickets are resolved, the cash balance matches the database and all the output files are created properly.

2nd Prompt: Not needed

#Problem 10: Reflection
Prompt:
Can you update the Reflection tab in output/desk_tickets.html and answer all the questions based on the agent system we built and the 3 tickets 101, 102 and 103 that we resolved.
Check the Expected and Actual sections for each ticket, the Cash tab and output/audit_trail.json before writing the answers.
The Reflection tab should include the following:
- How well the agents performed on each ticket and why
- For each ticket, compare what we expected the agents to do with what they actually did
- What parts of the process could have been handled more easily by a single agent using MCP tools instead of multiple agents and why
- Give 3 new problems Campus Customs might face that our current agent team can solve using the existing tools
- Give 3 new problems Campus Customs might face that our current agent team cannot solve with the existing tools
- For the problems we cannot solve, explain which additional agents and MCP tools we would need and why
Make sure the answers are detailed and based on what actually happened during the ticket runs. Include examples from the tickets, which agents were involved, what tools they used and whether the results matched our expectations.
Also use the Cash tab where relevant to explain how the agents handled payments and approvals.
Keep the answers in simple language and avoid generic explanations. I want the reflection to focus on our Campus Customs system and what we learned from building and testing it.
Don't change the other tabs or the information we already recorded.
In the end, check that the Reflection tab is updated properly and all the answers are included.

2nd Prompt: Not needed

#Problem 11: Submit to GitHub
Prompt:
Can you prepare our Campus Customs project and push it to a public GitHub repository so it can be submitted for grading.
Before pushing, check that all the files we created in the previous problems are included and the project structure is correct.
Make sure the repository includes the following:
- AI_prompts.md with all the prompts used in this homework
- requirements.txt with all Python dependencies
- .env.example with the required environment variables but no actual API keys
- .gitignore to exclude .env, node_modules and other unnecessary files
- .mcp.json with the MCP server configuration
- README.md with instructions to set up and run the project
- Both data/campus_customs.db and data/campus_customs_new.db
- mcp_server/ with server.py and README.md
- backend/ with main.py, models.py and all 5 agent prompt files
- frontend/ with the complete React dashboard
- output/ with harness.md, mcp_smoke.json, desk_tickets.html, design.md, resolved_tickets.json, resolved_board.html and audit_trail.json
Also create or update README.md and explain the following:
- How to install the required dependencies
- How to copy the original database to the working database for a fresh run
- How to configure the environment variables
- How to start the MCP server
- How to start the FastAPI backend
- How to start the React dashboard
- How to reset the database and run all 3 tickets again
Make sure no actual API keys or secrets are pushed to GitHub.
Once everything is ready, push the project to a public GitHub repository.
Save the repository URL in output/github_url.txt.
In the end, check that the repository is public, all required files are included and the README instructions are correct.
Give me the GitHub URL so I can submit it on Canvas.

2nd Prompt: Not needed
