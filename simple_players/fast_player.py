from pypokerengine.players import BasePokerPlayer
from pypokerengine.utils.card_utils import gen_cards
import numpy as np
import pandas as pd
from hand_evaluation.hand_evaluator import win_rate2 as estimate_hole_card_win_rate
from pypokerengine.engine.card import Card

NB_SIMULATION = 1000
FOLD = 0
CALL = 1
MIN_RAISE = 2
MAX_RAISE = 3
PRINT = False


card_rank_map = {'2': 2,
                 '3': 3,
                 '4': 4,
                 '5': 5,
                 '6': 6,
                 '7': 7,
                 '8': 8,
                 '9': 9,
                 'T': 10,
                 'J': 11,
                 'Q': 12,
                 'K': 13,
                 'A': 14}


class OtherPlayer:

    def __init__(self):
        self.streets = dict()
        self.streets['flop'] = 0
        self.streets['turn'] = 0
        self.streets['river'] = 0
        self.actions_count = 0
        self.wins = []
        self.stack = 0

class FastPlayer(BasePokerPlayer):

    def __init__(self,
                 p1=(1.5, 0.65),
                 p2=(0.6, 0.8),
                 p3=(1, 0.5),
                 p4=(1.5, 0.65),
                 p5=(1, 0.5),
                 p6=(0.6, 0.8),
                 p7=1.5,
                 p8=(1, 0.5),
                 p9=(0.6, 0.8),
                 use_adaptive = True
                 ):
        self.params = [p1, p2, p3, p4, p5, p6, p7, p8, p9]
        self.start_stack = 0
        self.actions_in_game = 0
        self.global_stack = 0
        self.global_random = 0
        self.players_stats = dict()
        self.there_is_allin = False
        self.round = 0
        self.game_updates = 0
        self.previous_action = FOLD
        self.previous_street = None
        self.bank_history = []
        self.seats = []
        self.did_action = False
        self.player_pos = 0
        self.strength_dict = pd.read_pickle('simple_players/strength_dict.pkl')
        self.array = pd.read_pickle('simple_players/Array.pkl')
        self.use_adaptive = use_adaptive
        self.street_counts = dict()
        self.street_counts['flop'] = 0
        self.street_counts['turn'] = 0
        self.street_counts['river'] = 0

    def declare_action(self, valid_actions, hole_card, round_state):

        stack = 0
        current_players = 0
        current_players_uuids = []

        # find active players
        for i in round_state['seats']:
            if self.uuid == i['uuid']:
                stack = i['stack']
            if i['state'] == 'participating':
                current_players+=1
                if self.uuid!= i['uuid']:
                    current_players_uuids.append(i['uuid'])

        if current_players < 2:
            current_players = 2

        community_card = round_state['community_card']
        if round_state['street'] != 'preflop':
            win_rate = 0
            for i in current_players_uuids:

                # calculate number of cards combinations for other players
                comb_cards = 169
                if self.players_stats[i].streets[round_state['street']] == 0:
                    comb_cards = 169
                else:
                    comb_cards = max(int(0.2*169), int(169*((self.players_stats[i].streets[round_state['street']])/(self.street_counts[round_state['street']]))))

                win_rate += estimate_hole_card_win_rate(
                    NB_SIMULATION,
                    self.array,
                    hole_card,
                    community_card,
                    comb_cards,
                    1
                )

            if len(current_players_uuids) == 0:
                b = 1
            else:
                b = len(current_players_uuids)

            win_rate /= b

        self.actions_in_game +=1

        if stack == 0:
            stack = 1

        on_the_big_blind = round_state['seats'][round_state['big_blind_pos']]['uuid'] == self.uuid
        on_the_small_blind = round_state['seats'][round_state['small_blind_pos']]['uuid'] == self.uuid

        if round_state['street'] == 'preflop':
            action, amount = self.__preflop_strategy(valid_actions, hole_card, round_state)
            self.did_action = True
            return action, amount
        else :

            action = self.select_action(win_rate, round_state, on_the_big_blind, on_the_small_blind, current_players,valid_actions, stack, current_players_uuids)
            self.previous_action = action

            if FOLD == action:
                if PRINT:
                    print("{} fold".format(round_state['street']), self.actions_in_game)

                return valid_actions[0]['action'], valid_actions[0]['amount']
            elif CALL == action:
                if PRINT:
                    print("{} call {}".format(round_state['street'], valid_actions[1]['amount']))

                return valid_actions[1]['action'], valid_actions[1]['amount']
            elif (MIN_RAISE == action or MAX_RAISE == action) and \
                    (valid_actions[2]['amount']['min'] == -1 or valid_actions[2]['amount']['max'] == -1):

                # there are some bugs in the implementation of pypokerengine
                if valid_actions[2]['amount']['min'] == -1:
                    if PRINT:
                        print("{} call {}".format(round_state['street'],  valid_actions[1]['amount']))

                return valid_actions[1]['action'], valid_actions[1]['amount']

            elif MIN_RAISE == action:
                if PRINT:
                    print("{} raise {}".format(round_state['street'], valid_actions[2]['amount']['min']))

                return valid_actions[2]['action'], valid_actions[2]['amount']['min']

            elif MAX_RAISE == action:
                if PRINT:
                    print("{} allin {}".format(round_state['street'], valid_actions[2]['amount']['max']))

                return valid_actions[2]['action'], valid_actions[2]['amount']['max']
            else:
                raise Exception("Invalid action [ %s ] is set" % action)

    def receive_game_start_message(self, game_info):
        self.nb_player = game_info['player_num']
        stack = 0
        self.players_stats = dict()
        for i in game_info['seats']:
            if self.uuid == i['uuid']:
                stack = i['stack']
            else:
                self.players_stats[i['uuid']] = OtherPlayer()

        self.start_stack = stack
        self.global_stack = stack
        self.global_random = np.random.randint(10)
        self.seats = game_info['seats']
        self.player_pos = self.__find_pos_by_uuid(self.uuid)

    def receive_round_start_message(self, round_count, hole_card, seats):
        self.actions_in_game=0
        self.there_is_allin = False
        self.bank_history = []
        self.did_action = False
        pass

    def receive_street_start_message(self, street, round_state):
        # collect enemies stats
        for i in round_state['seats']:
            if i['uuid'] != self.uuid and street != 'preflop':
                self.players_stats[i['uuid']].streets[street] +=1
        if street != 'preflop':
            self.street_counts[street]+=1

    def receive_game_update_message(self, action, round_state):
        self.game_updates+=1
        self.bank_history.append(round_state['pot']['main']['amount'])

    def receive_round_result_message(self, winners, hand_info, round_state):
        stack = 0
        for i in round_state['seats']:
            if self.uuid == i['uuid']:
                stack = i['stack']
        if PRINT:
            print("actions in game",self.actions_in_game, "points", stack - self.global_stack)
        self.global_stack = stack
        self.round +=1

    def select_action(self, win_rate, round_state, on_the_big_blind, on_the_small_blind, current_players, valid_actions, stack, current_players_uuids):
        action = FOLD

        # parameters for strategy optimized by hyperopt
        p1, p2, p3, p4, p5, p6, p7, p8, p9 = self.params

        if win_rate >= 0.85 and (round_state['street'] == 'river' or round_state['street'] == 'turn'):
            action = MAX_RAISE

        elif round_state['street'] == 'flop' and self.previous_action == MIN_RAISE and self.previous_street == 'flop':
            action = CALL
        # case1
        elif round_state['street'] == 'flop' and win_rate >= p1[0] /current_players and valid_actions[1]['amount']/stack < p1[1]:
            action = MIN_RAISE
        #case 2
        elif round_state['street'] == 'flop' and win_rate >= p2[0] and valid_actions[1]['amount']/stack < p2[1]:
            action = CALL
        #case 3
        elif round_state['street'] == 'flop' and win_rate >= p3[0] /current_players and valid_actions[1]['amount']/stack < p3[1]:
            action = CALL

        elif round_state['street'] == 'turn' and self.previous_action == MIN_RAISE and self.previous_street == 'turn':
            action = CALL
        # case 4
        elif round_state['street'] == 'turn' and win_rate >= p4[0] /current_players and valid_actions[1]['amount']/stack < p4[1]:
            action = MIN_RAISE
        # case 5
        elif round_state['street'] == 'turn' and win_rate >= p5[0] /current_players and valid_actions[1]['amount']/stack < p5[1]:
            action = CALL
        # case 6
        elif round_state['street'] == 'turn' and win_rate >= p6[0] and valid_actions[1]['amount']/stack < p6[1]:
            action = CALL

        elif round_state['street'] == 'river' and self.previous_action == MIN_RAISE and self.previous_street == 'river':
            action = CALL
        #case 7
        elif round_state['street'] == 'river' and win_rate >= p7 /current_players:
            action = MIN_RAISE
        #case 8
        elif round_state['street'] == 'river' and win_rate >= p8[0] /current_players and valid_actions[1]['amount']/stack < p8[1]:
            action = CALL
        #case 9
        elif round_state['street'] == 'river' and win_rate >= p9[0] and valid_actions[1]['amount']/stack < p9[1]:
            action = CALL

        elif valid_actions[1]['amount'] == 0:
            action = CALL

        else:
            action = FOLD

        if (action == MAX_RAISE or action == MIN_RAISE) and (valid_actions[2]['amount']['max'] == -1 or valid_actions[2]['amount']['min'] == -1):
            action = CALL

        self.previous_street = round_state['street']

        return action


    def __preflop_strategy(self, valid_actions, hole_card, round_state):
        fold_action, call_action, raise_action = valid_actions
        strength = self.__calc_hole_straights(hole_card)

        pos = self.__calc_relative_pos(self.player_pos, round_state['big_blind_pos'])
        # return 'fold',0


        if call_action['amount'] == 30:
            if (pos > 7 and strength > 0.445):
                action, amount = 'raise', min(120, raise_action['amount']['max'])
            elif (4 < pos <= 7 and strength > 0.26) :
                action, amount = 'raise', min(90, raise_action['amount']['max'])
            elif (2 < pos <= 4 and strength > 0.26) :
                action, amount = 'raise', min(60, raise_action['amount']['max'])
            elif (pos == 2 and strength > 0.26):
                action, amount = 'raise', min(90, raise_action['amount']['max'])
            elif pos == 1:
                if strength > 0.33:
                    action, amount = 'raise', min(90, raise_action['amount']['max'])
                else:
                    action, amount = 'call', call_action['amount']
            else:
                action, amount = 'fold', 0
        elif call_action['amount'] > 30 and not self.did_action:
            raiser_pos, raiser_amount = self.__calc_first_raiser_relative_pos(round_state, round_state['big_blind_pos'])
            if call_action['amount'] < 200:
                if raiser_pos > 6:
                    if strength > 0.55:
                        action, amount = 'raise', min(raise_action['amount']['min'] + 100,
                                                      raise_action['amount']['max'])
                    elif strength > 0.47:
                        action, amount = 'call', call_action['amount']
                    else:
                        action, amount = 'fold', 0
                elif 4 < raiser_pos <= 6:
                    if strength > 0.47:
                        action, amount = 'raise', min(raise_action['amount']['min'] + 100,
                                                      raise_action['amount']['max'])
                    elif strength > 0.33:
                        action, amount = 'call', call_action['amount']
                    else:
                        action, amount = 'fold', 0
                else:
                    if strength > 0.33:
                        action, amount = 'raise', min(raise_action['amount']['min'] + 100,
                                                      raise_action['amount']['max'])
                    else:
                        action, amount = 'fold', 0
            else:
                if strength > 0.8:
                    action, amount = 'raise', raise_action['amount']['max']
                elif strength > 0.51:
                    action, amount = 'call', call_action['amount']
                else:
                    action, amount = 'fold', 0

        else:  # amount > 30 and did_action = True
            if strength > 0.8:
                action, amount = 'raise', raise_action['amount']['max']
            elif strength > 0.51:
                action, amount = 'call', call_action['amount']
            else:
                action, amount = 'fold', 0

        if action == 'raise' and amount == -1:
            action, amount = 'call', call_action['amount']

        return action, amount

    def __calc_hole_straights(self, hole_card):
        rank0 = card_rank_map[hole_card[0][1]]
        rank1 = card_rank_map[hole_card[1][1]]

        combination = (hole_card[0][1] + hole_card[1][1] if rank0 < rank1 else hole_card[1][1] + hole_card[0][1]) \
                      + ('s' if hole_card[0][0] == hole_card[1][0] else '')
        return self.strength_dict[combination]

    def __calc_relative_pos(self, player_pos, big_blind_pos):
        if player_pos == big_blind_pos:
            return 1

        # seats = self.seats.copy()
        if player_pos > big_blind_pos:
            big_blind_pos += len(self.seats)

        counter = 0
        for idx in range(player_pos, big_blind_pos + 1):
            if self.seats[idx%len(self.seats)]['stack'] > 0:
                counter += 1
        return counter

    def __find_pos_by_uuid(self, uuid):
        return [idx for idx, seat in enumerate(self.seats) if seat['uuid'] == uuid][0]

    def __calc_first_raiser_relative_pos(self, round_state, big_blind_pos):
        raise_actions = [action for action in round_state['action_histories']['preflop'] if action['action'] == 'RAISE']
        if len(raise_actions) > 0:
            action = raise_actions[0]
            uuid = action['uuid']
            pos = self.__find_pos_by_uuid(uuid)
            relative_pos = self.__calc_relative_pos(pos, big_blind_pos)
            return relative_pos, action['amount']
        return None

