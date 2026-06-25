# > nami protocol
# basically its a dict with type#commmand -> outcome

command = {"request": "play"}
command_response = {"response": "music is playing"}

command_2 = {"request": "select", "name": "music or id"}
command_2_response = {"response": "music selected"}

# Datbase add -> music , playlist
command_1 = {"request": "database", "action": "refresh"}
command_1_response = {"response": "database refreshed!"}
