# Brain Dump - Product Vision and Open Questions
## Source: Speech-to-text transcription (Feb 2026)

---

## The Big Idea

Automate stock analysis for small and medium cap stocks from the Indian stock market (NSE or BSE).

In traditional setups, usually there is a team that scans for news or the press releases that come to BSE press release page or other places. Someone reads about them and decides whether it is worth acting on or not. If it is, they will employ other people or seek help from other people to find the worth in the news article or the press release or the quarterly statement of the company. Basically, any new information coming about the company somebody has to go ahead and do the hard work.

In traditional sense, we have always had human capital issue, so not everybody can follow all the SMEs (small and medium cap stocks). That probably left a lot of money on the table. Whoever could do it invested in it and made good money. In a lot of other cases, a lot of people kind of couldn't do it and yeah that's about the whole process.

If you think traditionally, people have had a whole set of teams like preliminary investigators - these could be junior analysts who decide or show it to senior analysts who look at this document, "Is it worth investigating or working on?" The senior guy finds it worthy and takes control of that and asks for other people in the team whether this information is worth hitting on. They would most probably look at the past data, the sector's information, or how the economy is doing and innovation coming in. Is the company being lying about their future projections and order books? And other related terms in the past or not?

## The Product Idea

What my core idea believes that most of these humans-in-the-loop in this process can be mapped with agentic solutions that have LLMs taking decisions and have tools at their disposal. In some cases, these agents talk to other agents and come up with the final analysis.

This is how I am envisioning the flow of the application going.

### Layer 1: Trigger Events
These are the kinds of events that trigger the investigation in the system:
- Press releases in NSE or BSE
- A tweet or pre-configured users in Reddit or pre-configured subreddits
- News sources and human triggers as well. The human trigger will probably be treated with a lot more seriousness because we know humans are generally smarter than machines, and they can do better than what machines are doing in certain things. Read it as intuition is an important thing.
- Unusual market activities may trigger an investigation, but this will probably not be specific to an event

### Layer 2: Worth Reviewing
This is a layer where we decide if we want to expand the computing power on going deeper on the trigger or just shut it off. A lot of unnecessary noise in terms of news and other things come from the press releases as well as tweets and other things. This is an intelligent system that will kind of cut short the loop and not engage on a more serious level from this trigger.
- Filters on sectors and companies that we are interested in are quite possible. We are not interested in the entire domain, we are only interested in certain sectors and companies. If the news affects those companies or sectors, we go ahead; otherwise, we drop the ball.
- This could have keyword match as well as AI review once the filter is passed to see if it is really worth doing or not.
- Human-triggered investigation should bypass this layer as we assume that if the human has triggered an event, it is definitely worth reviewing. So the answer is definitely yes for the event trigger type is human.

### Layer 3: Anything Significant
This is a layer where the AI will go deep into the investigation of what the trigger is and any other significant information that has come about it or can be searched on the web to find out if we have enough juice for it to affect our financial decision, or does it make in a positive way or negative way, or any change in our investment decision about this company or the companies in the domain or sector. These will be:
- Past emissions of data [NOTE: likely means "past releases/versions of data"]
- Any previous recommendations or summaries that we have about it
- The web search about the questions that we make it based on the content of the input
- The sector or industry analysis reports whether this company has anything significant in that sector or not
- Market data like P/E ratios, how invested FIIs are, or any other technical or fundamental signal that we can get from the market

### Layer 4: Does the News Have the Potential to Update Financial Decision-Making
Things like whether we should update the buy/sell or hold decisions. Maybe let's stick to just buy or sell decisions based on this news and other information that we gathered about it in that process of investigation in earlier layers. We combine all that and decide whether it will impact the final decision. If yes, we pass the judgment of buy and sell, and it goes as a report to human reviewer for making the call.

Interesting bit on this layer is that this should also contain investigations about related things that we have done in the past. Probably we found it worth reviewing or found it in "anything significant" but didn't affect any financial decision. If we reviewed the past investigations and combine that with this new information, maybe our decision gets impacted by the earlier analysis as well.

### Layer 5: The Verdict
Goes to the humans as a report.

---

## Open Questions

### What will the storage layer look like?
- Do I need vector databases? Most probably yes.
- Do I need time series? Maybe.
- Wide column or Mongo kind of database? Most probably yes.
- I want to limit Postgres or SQL only for the control plane because most of the things are dynamic, and on top of that, I don't have full clarity. Starting with SQL usually means getting tied down to what your storage layer looks like, and that kind of dictates the feature.
- I'm very positive that a Graph DB will probably help us a lot here. As industries, sectors, companies, among each other, and via sectors, industries, and market caps are linked to each other, so they are a well-defined ontology of the domain.

### How does data get accessed from the storage layer?

### Should we put a dedicated control plane which will handle access control, static data, logging, feedback loops, and other things?
The control plane will decide the access layer as well. Here, the access layer is for humans as well as bots because we want to allow certain types of stored data to certain agents and not to other agents.

### Agent Architecture Questions
- What is the agent-to-application flow like? Should we have one or more agents that can only talk to the agents in the same layer, and of course maybe in the data layer of agents from one layer and talk to agents in the previous?
- Is it better to have a single agent and tools within a layer, or multiple agents?
- If multiple agents, does it make sense to have a master agent that receives the query from the earlier domain or layer and engages the agents in this layer and passes the control to the master agent of next layer?
- How do we decide the flow of events or news that could affect the entire sector or the market?
