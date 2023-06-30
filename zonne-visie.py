# Initial settings

import streamlit as st
import os
import re
import numpy as np
import pandas as pd
import ast
import random
import folium
from streamlit_folium import st_folium
from streamlit_option_menu import option_menu
from geopy.geocoders import Nominatim
from googletrans import Translator
import warnings

warnings.filterwarnings( "ignore")

# Link to CSS file
with open('style.css')as f:
   st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html = True)

# Links and data paths
imagepath = "front_end/images/"
datapath = "front_end/data/"

df_sol_consum_street_region_2019 = pd.read_csv(os.path.join(datapath, "energy_consum_street_region_2019.csv"))
energy_consumption = df_sol_consum_street_region_2019[["hhld_id", "Street", "latitude", "longitude", \
                                                       "Approximate consumption (kWh)"]] \
                                                        .rename(columns={"Approximate consumption (kWh)": "energy_consumption"}) \
                                                        .set_index("hhld_id")
energy_communities = pd.read_csv(os.path.join(datapath, "recommended_energy_communities.csv"), index_col=0)
for col in ["pv_latitude", "pv_longitude", "pv_production", "installation_cost", "carbon_emission", "energy_consumption", "households"]:
    energy_communities[col] = energy_communities[col].apply(ast.literal_eval)

# Translation function
def translate_text(text, target_language):
    """
    Function which translates and returns translated text
    """
    translator = Translator()
    translation = translator.translate(text, dest=target_language)
    return translation.text

#### Application starts
st.sidebar.image(os.path.join(imagepath, 'solar-panels.png'), width=200)
st.sidebar.image(os.path.join(imagepath, 'zonne-visie-text.png'))
st.sidebar.write('Welcome to the Solar Vision App')

page_names = ['Energy Community Recommendations', 'Useful Links']
with st.sidebar:
    page = option_menu("Go to page:", page_names, 
                       icons=['house', 'list-task'], 
                       menu_icon='cast')

language_selection = st.sidebar.selectbox("Choose language:", ['en', 'nl', 'fr', 'tr', 'ar'])

# Main Window
title = 'Energy Community Recommendations'

if language_selection == 'en':
    st.title(':blue['+title+']')
else:
    st.title(':blue['+translate_text(title, language_selection)+']')

if page == 'Energy Community Recommendations':
    st.image(os.path.join(imagepath, 'networking.png'), width=250)

    # Intro text
    intro = 'Using this app, you can get recommendations for starting or joining a solar energy community with nearby citizens. ' \
             'Once you enter your address, you will get the recommended energy community members, number of solar panels and their locations, ' \
             'initial investment in Euro, potential net saving, and the amount of carbon emissions that your household can reduce by joining the community.'
    if language_selection == 'en':
        st.write(intro)
    else:
            st.write(translate_text(intro, language_selection))

    #### Functions for getting info for one household

    # Function for randomly choosing one household on a given street
    def choose_household(energy_consumption, street_name):

        # Find households on this street
        street_households = energy_consumption.loc[energy_consumption["Street"] == street_name.upper()]

        # Pick one at random
        random.seed(2506)
        hhld_id = street_households.index[random.randint(0, len(street_households)-1)]

        return hhld_id


    # Function for identifying the recommended energy community that a household belongs to
    def find_household(energy_communities, hhld_id):

        # Find the energy community which contains the household ID
        loc = np.where(energy_communities["households"].apply(lambda x: hhld_id in x))[0]
        assert len(loc)==1, f"Error: have found {len(loc)} energy communities which contain household{hhld_id}"
        ec_id = energy_communities.index[loc[0]]

        # Find which position in the energy community lists this household occupies
        loc = np.where([x==hhld_id for x in energy_communities.loc[ec_id, "households"]])[0]
        assert len(loc)==1, f"Error: have found {len(loc)} households in energy community #{ec_id} which correspond to household{hhld_id}"
        hhld_loc = loc[0]

        return ec_id, hhld_loc


    # Function for calculating annualised profit
    def calculate_annualised_profit_per_member(pv_production: list,
                                               energy_consumption: list,
                                               member: int,
                                               pv_cost: list,
                                               pv_lifespan: float,
                                               feed_in_tariff: float,
                                               grid_price: float,
                                               fixed_fee: float,
                                               community_price: float):

        # Number of members (households / access points)
        n_members = len(energy_consumption)

        # Number of solar panels
        n_pvs = len(pv_production)

        # Total electricity consumption of all members
        total_energy_consumption = sum(energy_consumption)

        # Total electricity production of all solar panels
        total_pv_production = sum(pv_production)

        # Fraction of total electricity consumption which comes from target member
        member_energy_fraction = energy_consumption[member] / total_energy_consumption

        # How much members are currently paying for their electrcity
        counterfactual_price = total_energy_consumption * grid_price + fixed_fee

        # How much members would pay for their own generated electricity (remember they may not generate enough to supply all their consumption)
        cost_of_energy_at_community_price = min([total_pv_production, total_energy_consumption]) * community_price

        # How much members would pay for electricity from the grid (this is the shortfall between production and consumption)
        cost_of_energy_at_grid_price = max([0, total_energy_consumption - total_pv_production]) * grid_price

        # How much energy community could earn from selling surplus back to the grid, after consuming what they need
        revenue = max([0, total_pv_production - total_energy_consumption]) * feed_in_tariff

        # How much the solar panels cost
        initial_cost = sum(pv_cost)
        annualised_cost = initial_cost/pv_lifespan

        # Profit derived from the above calculations
        profit = counterfactual_price - sum([cost_of_energy_at_community_price, cost_of_energy_at_grid_price]) + revenue - annualised_cost

        # Calculate for the target member
        member_counter_factual_price = energy_consumption[member] * grid_price + fixed_fee
        member_cost_energy_community = cost_of_energy_at_community_price * member_energy_fraction
        member_cost_energy_grid = cost_of_energy_at_grid_price * member_energy_fraction
        member_revenue = revenue/n_members
        member_cost = annualised_cost/n_members
        member_profit = member_counter_factual_price - sum([member_cost_energy_community, member_cost_energy_grid]) + member_revenue - member_cost

        # Divide profit equally between members
        if n_members==0:
          ave_profit_per_member = 0
        else:
          ave_profit_per_member = profit / n_members

        return member_profit


    # Calculate member's initial investment
    def calculate_startup_cost_per_member(energy_community):

        # Assume installation cost is shared equally between all members
        cost = np.sum(energy_community["installation_cost"])/len(energy_community["households"])

        return cost


    # Calculate member's carbon emissions reduction
    def calculate_carbon_reduction(energy_community, member):

        # Total electricity consumption of all members
        total_energy_consumption = sum(energy_community["energy_consumption"])

        # Total electricity production of all solar panels
        total_pv_production = sum(energy_community["pv_production"])

        # Total carbon emissions reduction from all solar panels:
        total_carbon_reduction = sum(energy_community["carbon_emission"])

        # Fraction of total electricity consumption which comes from target member
        member_energy_fraction = energy_community["energy_consumption"][member] / total_energy_consumption

        # Calculate target member's share of the carbon emissions reduction
        if total_energy_consumption >= total_pv_production:
            # All solar panel electricity is consumed by members
            member_carbon_reduction = total_carbon_reduction * member_energy_fraction
        else:
            # Only some of the solar panel electricity is consumed by members
            member_carbon_reduction = (total_energy_consumption / total_pv_production) * total_carbon_reduction * member_energy_fraction

        return member_carbon_reduction


    # Combine the above into one function
    def calculate_benefits(energy_communities, energy_consumption, street_name):

        # Choose a household on the street
        hhld_id = choose_household(energy_consumption, street_name)

        # Find the household's energy community
        ec_id, target_member = find_household(energy_communities, hhld_id)
        energy_community = energy_communities.loc[ec_id]

        # Get number of households and solar panels
        n_households = len(energy_community["households"])
        n_solar_panels = len(energy_community["pv_production"])

        # Member's required investment
        cost = calculate_startup_cost_per_member(energy_community=energy_community)

        # Member's annualised profit
        annualised_profit = calculate_annualised_profit_per_member(pv_production=energy_community["pv_production"],
                                            energy_consumption=energy_community["energy_consumption"],
                                            member=target_member,
                                            pv_cost=energy_community["installation_cost"],
                                            pv_lifespan=20,
                                            feed_in_tariff=0,
                                            grid_price=14.94,
                                            fixed_fee=25,
                                            community_price=13)

        # Member's reduction in carbon emissions
        carbon = calculate_carbon_reduction(energy_community=energy_community, member=target_member)

        return n_households, n_solar_panels, cost, annualised_profit, carbon


    #### Show Results

    street = ""

    # Get input address
    address = st.text_input("Enter your address:")

    # Select a street
    # street = "Weerstandsplein"
    # street = "Breendonkstraat"
    street = re.sub('[^a-zA-Z]+', '', address)

    if street == "":
        st.write("Please enter your address above to get results.")
    else:
        # Do calculations
        n_households, n_solar_panels, startup_cost, annualised_profit, carbon = calculate_benefits(energy_communities, energy_consumption, street)

        # Round up
        startup_cost = round(startup_cost, 2)
        annualised_profit = round(annualised_profit, 2)
        carbon = round(carbon, 2)
        trees = int(round(carbon/21, 0))

        # Show metrics in columns
        col1, col2, col3 = st.columns(3)
        col1.metric(label="Community Members", value=(round(n_households, 2)))
        col2.metric(label="Solar Panels", value=n_solar_panels)
        col3.metric(label="Initial Investment (€)", value=startup_cost)

        col4, col5, col6 = st.columns(3)
        col4.metric(label="Net Savings (€)", value=annualised_profit)
        col5.metric(label="Emissions Reduction (kg CO2)", value=carbon)
        col6.metric(label="Emissions Reduction (trees)", value=trees)

        # Print
        text_1 = f"Great news! We have found an energy community for you.\nWe suggest partnering with {n_households-1} of your neighbours and installing solar panels at {n_solar_panels} locations together. Don't worry, we can help with that."
        text_2 = f"For an initial investment of €{startup_cost:,.2f}, you could see net savings of €{annualised_profit:,.2f} per year over the next 20 years."
        text_3 = f"Your household could also reduce carbon emissions by {carbon:.1f} kg CO2 per year: that's similar to the carbon emissions reduced by {carbon/21:.0f} mature trees for a year."
        
        if language_selection == 'en':
            st.write(text_1 + text_2 + text_3)
        else:
            st.write(translate_text(text_1 + text_2 + text_3, language_selection))
        
        # Plot map with energy communities

        # Plot Ghent
        ghent_map = folium.Map(location=[51.0540, 3.6980], width="80%", height="80%", zoom_start=15)

       # Choose an energy community
        street = street
        hhld_id = choose_household(energy_consumption, street)
        ec_id, hhld_loc = find_household(energy_communities, hhld_id)
        ec = energy_communities.loc[ec_id]

        # Plot proposed member locations
        for hh in ec["households"]:
            # Plot a pin for each solar panel
            folium.Marker(
                location=[energy_consumption.loc[hh, "latitude"], energy_consumption.loc[hh, "longitude"]],
                icon=folium.Icon(color="blue", icon="home")
                ).add_to(ghent_map)

        # Plot proposed solar panel locations
        for pv in range(len(ec["pv_latitude"])):
            # Plot a pin for each solar panel
            folium.Marker(
                location=[ec["pv_latitude"][pv], ec["pv_longitude"][pv]],
                icon=folium.Icon(color="green", icon="solar-panel", prefix="fa")
                ).add_to(ghent_map)

        st_data = st_folium(ghent_map, width=800)



elif page == 'Useful Links':
# elif selection == 'Useful Links':
    st.image(os.path.join(imagepath, 'solar-panels.jpg'))
    st.write("Useful Links")
    st.write("The government website: " + "https://stad.gent/en/city-governance-organisation/city-policy/ghents-climate-actions/futureproof-buildings")
    st.write("https://www.go-solar.be/")