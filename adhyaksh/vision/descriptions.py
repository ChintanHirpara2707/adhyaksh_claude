"""Two-sentence plain descriptions for the 80 COCO class names, plus optional Wikipedia lookup."""
from __future__ import annotations

import io
import json
import urllib.error
import urllib.parse
import urllib.request

import streamlit as st

COCO_NAMES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck",
    "boat", "traffic light", "fire hydrant", "stop sign", "parking meter", "bench",
    "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra",
    "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove",
    "skateboard", "surfboard", "tennis racket", "bottle", "wine glass", "cup",
    "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "TV", "laptop", "mouse",
    "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
    "hair drier", "toothbrush",
]

_DESCRIPTIONS = {
    "person": "A person is a human being. People walk, talk, work, and carry out daily activities.",
    "bicycle": "A bicycle is a two-wheeled vehicle you ride by pedaling. It is used for transport, exercise, and recreation.",
    "car": "A car is a four-wheeled motor vehicle for transport. It carries people and goods on roads.",
    "motorcycle": "A motorcycle is a two-wheeled motor vehicle. It is used for fast personal transport.",
    "airplane": "An airplane is a powered flying vehicle with wings. It transports people and cargo through the air.",
    "bus": "A bus is a large vehicle that carries many passengers. It runs on fixed routes in cities and between towns.",
    "train": "A train is a rail vehicle that runs on tracks. It carries passengers and freight over long distances.",
    "truck": "A truck is a motor vehicle designed to carry cargo. It hauls goods and materials over roads.",
    "boat": "A boat is a watercraft for travel on water. It is used for fishing, transport, and recreation.",
    "traffic light": "A traffic light signals when vehicles must stop or go. It controls the flow of traffic at intersections.",
    "fire hydrant": "A fire hydrant provides water for firefighting. Firefighters connect hoses to it during emergencies.",
    "stop sign": "A stop sign tells drivers to come to a full stop. It is placed at intersections to prevent collisions.",
    "parking meter": "A parking meter collects payment for parking time. Drivers pay to park in a space for a limited period.",
    "bench": "A bench is a seat for more than one person. It is found in parks, streets, and waiting areas.",
    "bird": "A bird is a feathered animal with wings. Birds fly, sing, and build nests.",
    "cat": "A cat is a small domesticated feline mammal. Cats are kept as pets and hunt small animals.",
    "dog": "A dog is a domesticated canine mammal. Dogs are kept as pets, guards, and working animals.",
    "horse": "A horse is a large hoofed mammal used for riding. Horses are used for transport, sport, and farm work.",
    "sheep": "A sheep is a domesticated ruminant with a woolly coat. Sheep provide wool, meat, and milk.",
    "cow": "A cow is a large domesticated bovine raised for milk or meat. Cows are a key source of dairy and beef.",
    "elephant": "An elephant is a very large mammal with a trunk. Elephants live in herds and use their trunks to feed and drink.",
    "bear": "A bear is a large heavy mammal with thick fur. Bears are omnivores found in forests and mountains.",
    "zebra": "A zebra is an African horse with black and white stripes. Zebras live in grasslands and savannas.",
    "giraffe": "A giraffe is a tall African mammal with a long neck. It feeds on leaves high in trees.",
    "backpack": "A backpack is a bag carried on the back with shoulder straps. It holds books, supplies, and personal items.",
    "umbrella": "An umbrella is a canopy held overhead for rain or sun. It keeps a person dry or shaded.",
    "handbag": "A handbag is a bag used for carrying personal items. It is held by hand or over the shoulder.",
    "tie": "A tie is a narrow piece of cloth worn around the neck. It is worn with formal shirts and suits.",
    "suitcase": "A suitcase is a rectangular case for clothes when traveling. It holds belongings for trips.",
    "frisbee": "A frisbee is a plastic disc thrown for recreation. People throw it to each other or to dogs.",
    "skis": "Skis are long narrow runners used for gliding over snow. They are used for downhill and cross-country skiing.",
    "snowboard": "A snowboard is a single board used for sliding on snow. Riders stand sideways and descend snowy slopes.",
    "sports ball": "A sports ball is a round object used in games. It is kicked, thrown, or hit in various sports.",
    "kite": "A kite is a lightweight frame covered with paper or cloth flown in wind. It is flown on a string for recreation.",
    "baseball bat": "A baseball bat is a smooth wooden or metal club used in baseball. Batters use it to hit the ball.",
    "baseball glove": "A baseball glove is a leather glove worn to catch a ball. Fielders wear it to catch and field.",
    "skateboard": "A skateboard is a board with wheels used for riding. It is used for sport and transport on paved surfaces.",
    "surfboard": "A surfboard is a long board used for riding waves. Surfers stand on it to ride ocean waves.",
    "tennis racket": "A tennis racket is an oval racket with a tight mesh used in tennis. Players hit the ball over a net.",
    "bottle": "A bottle is a container with a narrow neck used for liquids. It holds water, drinks, or sauces.",
    "wine glass": "A wine glass is a stemmed glass used for drinking wine. Its shape brings out the wine's aroma and flavor.",
    "cup": "A cup is a small round container used for drinking. It holds coffee, tea, or other hot or cold drinks.",
    "fork": "A fork is a utensil with prongs used for eating. It spears and lifts food to the mouth.",
    "knife": "A knife is a cutting tool with a sharp blade. It cuts food and other materials.",
    "spoon": "A spoon is a utensil with a shallow bowl used for eating. It scoops soup, cereal, and desserts.",
    "bowl": "A bowl is a round open container used for food or liquid. It holds soup, cereal, or rice.",
    "banana": "A banana is a long curved yellow fruit. It is eaten raw and is rich in potassium.",
    "apple": "An apple is a round fruit with red or green skin. It is eaten fresh or used in cooking and baking.",
    "sandwich": "A sandwich is two or more slices of bread with filling. It is a quick meal eaten cold or toasted.",
    "orange": "An orange is a round citrus fruit with orange skin. It is peeled and eaten or juiced.",
    "broccoli": "Broccoli is a green vegetable with a thick stalk and flower head. It is cooked or eaten raw as a nutritious side dish.",
    "carrot": "A carrot is a long orange root vegetable. It is eaten raw or cooked in many dishes.",
    "hot dog": "A hot dog is a sausage in a sliced bun. It is a popular fast food served with toppings.",
    "pizza": "A pizza is a flat dough base topped with cheese and sauce. It is baked and sliced into portions.",
    "donut": "A donut is a small fried or baked sweet dough ring. It is a sweet snack often topped with glaze.",
    "cake": "A cake is a sweet baked dessert made from flour and sugar. It is served at celebrations and with tea or coffee.",
    "chair": "A chair is a seat for one person with a back and legs. It is used for sitting at tables, desks, and elsewhere.",
    "couch": "A couch is a long upholstered seat for several people. It is used for sitting and relaxing in living rooms.",
    "potted plant": "A potted plant is a plant growing in a container. It is kept indoors for decoration and cleaner air.",
    "bed": "A bed is a piece of furniture used for sleeping. It has a mattress and frame for rest at night.",
    "dining table": "A dining table is a table used for eating meals. People gather around it to eat together.",
    "toilet": "A toilet is a fixture for disposal of bodily waste. It is found in bathrooms and restrooms.",
    "TV": "A TV is an electronic device that displays moving images and sound. It is used to watch shows, news, and movies.",
    "laptop": "A laptop is a portable computer with a screen and keyboard. It is used for work, study, and entertainment anywhere.",
    "mouse": "A mouse is a handheld device used to control a computer cursor. It is moved on a desk to point and click.",
    "remote": "A remote is a handheld device used to control equipment from a distance. It sends signals to TVs and other devices.",
    "keyboard": "A keyboard is a set of keys used to type into a computer or typewriter. It is used to enter text and commands.",
    "cell phone": "A cell phone is a portable telephone that connects over a network. It is used for calls, messages, and internet.",
    "microwave": "A microwave is an oven that heats food with electromagnetic waves. It quickly reheats or cooks food.",
    "oven": "An oven is a heated chamber used for baking or roasting food. It cooks food using dry heat.",
    "toaster": "A toaster is a small appliance that browns bread by heat. It makes toast from sliced bread.",
    "sink": "A sink is a basin with running water for washing. It is used to wash hands, dishes, and food.",
    "refrigerator": "A refrigerator is an appliance that keeps food cold. It preserves food by slowing spoilage.",
    "book": "A book is a set of printed pages bound together. It is read for information, stories, or study.",
    "clock": "A clock is a device that shows the time. It displays hours, minutes, and sometimes seconds.",
    "vase": "A vase is an open container used for holding cut flowers. It is used for home decoration.",
    "scissors": "Scissors are a cutting tool with two pivoted blades. They cut paper, fabric, and other thin materials.",
    "teddy bear": "A teddy bear is a soft toy stuffed bear. It is a child's comfort toy and gift.",
    "hair drier": "A hair drier is an electric device that blows air to dry hair. It is used after washing hair.",
    "toothbrush": "A toothbrush is a small brush used for cleaning teeth. It is used with toothpaste for oral hygiene.",
}

_WIKI_TITLES = {
    "mouse": "Computer mouse",
    "remote": "Remote control",
    "cell phone": "Mobile phone",
    "tv": "Television",
    "dining table": "Table (furniture)",
    "potted plant": "Houseplant",
    "sports ball": "Ball",
}


def describe(label: str) -> str:
    """Return a two-sentence description for a COCO label, with a fallback."""
    return _DESCRIPTIONS.get(label, f"A {label} is an object detected in the image. It is commonly seen in everyday scenes.")


@st.cache_data(ttl=3600)
def _wiki_fetch(title: str) -> str | None:
    """Fetch the first two sentences of a Wikipedia summary. Returns None on failure."""
    url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(title)
    req = urllib.request.Request(url, headers={"User-Agent": "Adhyaksh/1.0"})
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            data = json.loads(r.read().decode("utf-8"))
        extract = data.get("extract", "")
        sentences = [s.strip() for s in extract.split(". ") if s.strip()]
        summary = ". ".join(sentences[:2])
        if not summary.endswith("."):
            summary += "."
        page = data.get("content_urls", {}).get("desktop", {}).get("page", "")
        if page:
            summary += f"\n\n[More from Wikipedia]({page})"
        return summary
    except Exception:
        return None


def wikipedia(label: str) -> str:
    """Return a Wikipedia summary line for a label, or empty string if unavailable."""
    title = _WIKI_TITLES.get(label, label)
    summary = _wiki_fetch(title)
    if summary is None:
        return ""
    return "\n\n" + summary
