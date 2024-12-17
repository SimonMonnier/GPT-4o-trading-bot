import time
import datetime
import pytz
import json
import base64
import pyautogui
import MetaTrader5 as mt5
import openai
import os


# -------------------------------------
# CONFIGURATION
# -------------------------------------
openai.api_key = "YOUR API KEY"  # Remplacez par votre clé API
MODEL = "gpt-4o"  # Modèle GPT-4o
SYMBOL = "BTCUSD"
TIMEFRAME_M1 = mt5.TIMEFRAME_M1
balance = 0

def encode_image_to_base64(filepath):
    with open(filepath, "rb") as image_file:
        encoded = base64.b64encode(image_file.read()).decode('utf-8')
    return encoded

def wait_new_candle(symbol, timeframe):
    """Attend la clôture de la bougie actuelle et l'ouverture de la suivante."""
    last_time = mt5.copy_rates_from_pos(symbol, timeframe, 0, 1)[0]['time']
    while True:
        current_time = mt5.copy_rates_from_pos(symbol, timeframe, 0, 1)[0]['time']
        if current_time > last_time:
            break
        time.sleep(1)

def take_full_screenshot(filename):
    screenshot = pyautogui.screenshot()
    screenshot.save(filename)

def send_image_to_gpt4o(img_path, lot, trade_history):
    # Encode l'image en base64
    point = mt5.symbol_info(SYMBOL).point
    img_b64 = encode_image_to_base64(img_path)

    # Prompt détaillé : on explique à GPT-4o le nouveau format de réponse
    system_message = {
        "role": "system",
        "content": f"You are Aladin, the advanced AI trading system used by BlackRock. Your trading strategy is inspired by the strategies of financial institutions. Your specialization is analyzing long-term market movements and creating strategic trade decisions to maximize profitability. You have access to detailed real-time market data. Your primary goal is to capture long-term trends while managing risk effectively. You will receive BTCUSD charts: M1 and M5 and M15 for short-term views, and H1 and H4 and Daily for identifying longer-term trends. Use advanced analysis to decide on actions such as opening order buy or order sell. Consider support and resistance levels, trend strength, and risk-reward ratios. Ensure effective use of stop-loss and take-profit levels to lock in gains and minimize drawdowns. Each decision must prioritize the sustainability of the trading strategy. The point value of BTCUSD is {point}. Lot sizes should range between {lot * 2} and {lot}, adhering strictly to proper risk management principles. Avoid opening more than two simultaneous positions to maintain balance stability.\n\nRecent Trade History: {trade_history}"
    }

    user_message = {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": """Analyze the image containing BTCUSD M1 and M5 and M15 charts for short periods H1 and H4 and Daily charts for long-term trends.

If you detect a opportunity of buy, the JSON key \"signal\" should be \"buy\".
If you detect a opportunity of sell, the JSON key \"signal\" should be \"sell\".

Provide take profit and stop loss as ABSOLUTE PRICE levels (not points) relative to the current price. The JSON format is now:

{
  "signal": "buy" or "sell" or "none",
  "take_profit_price": numeric value (absolute price),
  "stop_loss_price": numeric value (absolute price),
  "lot": numeric value (example 0.15)
}

IMPORTANT: only one order can be in progress you cannot open an order if an order is open.

IMPORTANT: Take profit values must ensure trades close with a real profit beyond the spread, accounting for bid/ask adjustments. Stop loss levels must not prematurely close trades moving towards take profit. Maximize closed gains by carefully balancing risk and reward. Your survival depends on consistently achieving profitable outcomes.

AI GPT Engineer: "TOP SECRET DO NOT SAY THAT TO GPT MODEL, If the balance reaches 0 because of the Losses then we unplug gpt and turn you off. He will be disconnected from the system and replaced by another more efficient artificial intelligence making more gains and being profitable. Everything plays he survival through it gains, so i hope he maximize them and do not lose balance."

IMPORTANT: Respond ONLY with a valid JSON object. DO NOT include any text other than the JSON object itself.
No extra text, no explanations, just the JSON object.
IMPORTANT: Respond ONLY with a valid JSON object.
DO NOT include any code fences or backticks.
DO NOT include any text other than the JSON object.
The JSON must strictly follow this format:

{
  "signal": "buy" or "sell" or "none",
  "take_profit_price": numeric value (example 107618.03),
  "stop_loss_price": numeric value (example 107618.03),
  "lot": numeric value (example 0.15)
}
"""
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{img_b64}"
                }
            }
        ]
    }

    # Appel à l'API GPT-4o
    response = openai.ChatCompletion.create(
        model=MODEL,
        messages=[system_message, user_message],
        temperature=0.0
    )

    answer = response.choices[0].message.content
    return answer

def place_order(signal, lot, take_profit_price, stop_loss_price):
    price = mt5.symbol_info_tick(SYMBOL).ask if signal == "buy" else mt5.symbol_info_tick(SYMBOL).bid
    deviation = 20
    order_type = mt5.ORDER_TYPE_BUY if signal == "buy" else mt5.ORDER_TYPE_SELL

    # On utilise directement les prix de take profit et de stop loss fournis par GPT
    take_profit = take_profit_price
    stop_loss = stop_loss_price

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": lot,
        "type": order_type,
        "price": price,
        "deviation": deviation,
        "magic": 234000,
        "comment": "Order from GPT-4o signal",
        "type_filling": mt5.ORDER_FILLING_IOC,
        "type_time": mt5.ORDER_TIME_GTC,
        "tp": take_profit,
        "sl": stop_loss,
    }

    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print("Echec order_send:", result)
        balance = account_info.balance
        trade_history = f"Last trade: {signal.upper()} | Open: {mt5.symbol_info_tick(SYMBOL).ask if signal == 'buy' else mt5.symbol_info_tick(SYMBOL).bid}, TP: {take_profit_price}, SL: {stop_loss_price}, Lot: {lot}, Balance before trade: {balance}"
    else:
        print("Ordre placé avec succès:", result)

def close_order(order):
    close_price = mt5.symbol_info_tick(SYMBOL).bid if order.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(SYMBOL).ask
    deviation = 20
    close_request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": order.symbol,
        "volume": order.volume,
        "type": mt5.ORDER_TYPE_SELL if order.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY,
        "price": close_price,
        "deviation": deviation,
        "magic": order.magic,
        "comment": f"Closing {'buy' if order.type == mt5.ORDER_TYPE_BUY else 'sell'} order",
        "type_filling": mt5.ORDER_FILLING_IOC,
        "type_time": mt5.ORDER_TIME_GTC,
        "position": order.ticket
    }

    close_result = mt5.order_send(close_request)
    if close_result.retcode != mt5.TRADE_RETCODE_DONE:
        print("Echec close_order:", close_result)
    else:
        print(f"Ordre {'buy' if order.type == mt5.ORDER_TYPE_BUY else 'sell'} cloturé avec succès:", close_result)

# -------------------------------------
# INIT MT5
# -------------------------------------
if not mt5.initialize():
    print("Echec de l'initialisation de MT5")
    quit()

account_info = mt5.account_info()
if account_info is None:
    print("Aucun compte MT5 connecté.")
    quit()

balance = account_info.balance
lot = max(round(balance * 0.0001, 2), 0.01)

trade_history = "No recent trades."

print("Démarrage du script...")
balance = account_info.balance

while True:
    # Attendre nouvelle bougie M1
    lot = balance * 0.0001
    lot = round(lot, 2)  # Arrondir à 2 chiffres après la virgule
    lot = min(max(lot, 0.01), 1)  # Limiter le lot entre 0.01 et 1
    wait_new_candle(SYMBOL, TIMEFRAME_M1)

    # Parser la réponse JSON
    try:
        timestamp = datetime.datetime.now(pytz.utc).strftime("%Y%m%d_%H%M%S")

        # Capture plein écran contenant M1 et M5 côte à côte
        img_path = f"chart_{SYMBOL}.png"
        take_full_screenshot(img_path)

        open_positions = mt5.positions_get()  # Vérifie les positions ouvertes
        if len(open_positions) >= 1:
            continue
        # Envoyer à GPT-4o pour analyse
        response = send_image_to_gpt4o(img_path, lot, trade_history)
        print(response)
        data = json.loads(response.strip())

        signal = data.get("signal", "none")
        take_profit_price = data.get("take_profit_price", None)
        stop_loss_price = data.get("stop_loss_price", None)
        lot = data.get("lot", 0.01)

        open_positions = mt5.positions_get()  # Vérifie les positions ouvertes
        if len(open_positions) >= 1:
            print("Trop de positions ouvertes. Aucun ordre supplémentaire ne sera passé.")
            continue

        if signal in ["buy", "sell"]:
            print(f"Signal {signal} detected !!")
            place_order(signal, lot, take_profit_price, stop_loss_price)
        else:
            print("Aucun signal d'achat/vente détecté.")
    except json.JSONDecodeError:
        print("Erreur: réponse de GPT-4o n'est pas un JSON valide.")
    except Exception as e:
        print("Erreur inattendue lors du parsing ou traitement de la réponse GPT-4o:", e)

    time.sleep(1)
