# Other Features

## Tracing and Monitoring

You can view console logs in Azure portal. You can get the link to the resource group with the azd tool:

```shell
azd show
```

Or if you want to navigate from the Azure portal main page, select your resource group from the 'Recent' list, or by clicking the 'Resource groups' and searching your resource group there.

After accessing you resource group in Azure portal, choose your container app from the list of resources. Then open 'Monitoring' and 'Log Stream'. Choose the 'Application' radio button to view application logs. You can choose between real-time and historical using the corresponding radio buttons. Note that it may take some time for the historical view to be updated with the latest logs.

You can view the App Insights tracing in Azure AI Foundry. Select your project on the Azure AI Foundry page and then click 'Tracing'.

## AI Red Teaming Agent

The [AI Red Teaming Agent](https://learn.microsoft.com/azure/ai-foundry/concepts/ai-red-teaming-agent) is a powerful tool designed to help organizations proactively find security and safety risks associated with generative AI systems during design and development of generative AI models and applications.

In this [script](../airedteaming/ai_redteaming.py), you will be able to set up an AI Red Teaming Agent to run an automated scan of your agent in this sample. No test dataset or adversarial LLM is needed as the AI Red Teaming Agent will generate all the attack prompts for you.

To install required extra package from Azure AI Evaluation SDK and run the script in your local development environment:  

```shell
python -m pip install -r src/requirements.txt
python -m pip install azure-ai-evaluation[redteam]

python evals/airedteaming.py
```

Read more on supported attack techniques and risk categories in our [documentation](https://learn.microsoft.com/azure/ai-foundry/how-to/develop/run-scans-ai-red-teaming-agent).
