import random


rand_list = random.sample(range(1,21), 10)
print("Random List between 1 and 20: ", rand_list)

list_comprehension_below_10 = [num for num in rand_list if num < 10]
print("List comprehension if below 10:" , list_comprehension_below_10)

filter_below_10 = list(filter(lambda x: x < 10, rand_list))
print("User filter to print below 10:", filter_below_10)