
import commune as c
import os
import pandas as pd
from typing import *

class Vali(c.Module):
    whitelist = ['eval_module', 'score', 'eval', 'leaderboard']
    voting_networks = ['bittensor', 'commune']
    def __init__(self,
                    network= 'local', # for local subspace:test or test # for testnet subspace:main or main # for mainnet
                    netuid = 0, # (NOT LOCAL) the subnetwork uid or the netuid. This is a unique identifier for the subnetwork 
                    search=  None, # (OPTIONAL) the search string for the network 
                    max_network_staleness=  10, # the maximum staleness of the network # LOGGING
                    verbose=  True, # the verbose mode for the worker # EPOCH
                    batch_size= 64,
                    queue_size=  128,
                    max_workers=  None ,
                    score_fn = None, #EVAL
                    path= None, # the storage path for the module eval, if not null then the module eval is stored in this directory
                    alpha= 1.0, # alpha for score
                    timeout= 10, # timeout per evaluation of the module
                    max_staleness= 0, # the maximum staleness of the worker
                    epoch_time=  3600, # the maximum age of the leaderboard befor it is refreshed
                    min_leaderboard_weight=  0, # the minimum weight of the leaderboard
                    run_step_interval =  3, # the interval for the run loop to run
                    run_loop= True, # This is the key that we need to change to false
                    vote_interval= 100, # the number of iterations to wait before voting
                    module = None,
                    timeout_info= 4, # (OPTIONAL) the timeout for the info worker
                    miner= False , # converts from a validator to a miner
                    update=False,
                 **kwargs):
        config = self.set_config(locals())
        config = c.dict2munch({**Vali.config(), **config})
        self.config = config
        if update:
            self.config.max_staleness = 0
        self.sync_network()
        # start the run loop
        if self.config.run_loop:
            c.thread(self.run_loop)


    init_vali = __init__

    def score(self, module):
        return 'name' in module.info()

    def set_score_fn(self, score_fn: Union[Callable, str]):
        """
        Set the score function for the validator
        """
        module = module or self 
        if isinstance(score_fn, str):
            score_fn = c.get_fn(score_fn)
        assert callable(score_fn)
        self.score = getattr(self, score_fn)
        return {'success': True, 'msg': 'Set score function', 'score_fn': self.score.__name__}

    def init_state(self):
        self.executor = c.module('executor')(max_workers=self.config.max_workers,  maxsize=self.config.queue_size)
        self.requests = 0
        self.last_start_time = 0
        self.errors  = 0
        self.successes = 0
        self.epochs = 0
        self.last_sync_time = 0
        self.last_error = 0
        self.last_sent = 0
        self.last_success = 0
        self.start_time = c.time()
        self.results = []
        self.futures = []

    @property
    def sent_staleness(self):
        return c.time()  - self.last_sent

    @property
    def success_staleness(self):
        return c.time() - self.last_success

    @property
    def lifetime(self):
        return c.time() - self.start_time
    
    @property
    def is_voting_network(self):
        return any([v in self.config.network for v in self.voting_networks])
    
    @property
    def last_start_staleness(self):
        return c.time() - self.last_start_time

    def run_step(self):
        """
        The following runs a step in the validation loop
        """
        self.epoch()
        if self.is_voting_network and self.vote_staleness > self.config.vote_interval:
            c.print('Voting', color='cyan')
            c.print(self.vote())
        c.print(f'Epoch {self.epochs} with {self.n} modules', color='yellow')
        c.print(self.leaderboard())

    def run_loop(self):
        """
        The run loop is a backgroun loop that runs to do two checks
        - network: check the staleness of the network to resync it 
        - workers: check the staleness of the last success to restart the workers 
        - voting: check the staleness of the last vote to vote (if it is a voting network)
        
        """
        # start the workers

        while True:
            c.sleep(self.config.run_step_interval)
            try:
                self.run_step()
            except Exception as e:
                c.print(c.detailed_error(e))

    def age(self):
        return c.time() - self.start_time

    def get_next_result(self, futures=None):
        futures = futures or self.futures
        try:
            for future in c.as_completed(futures, timeout=self.config.timeout):
                futures.remove(future) 
                result = future.result()
                result['w'] = result.get('w', 0)
                did_score_bool = bool(result['w'] > 0)
                emoji =  '🟢' if did_score_bool else '🔴'
                if did_score_bool:
                    keys = ['w', 'name', 'address', 'latency']
                else:
                    keys = list(result.keys())
                result = {k: result.get(k, None) for k in keys if k in result}
                msg = ' '.join([f'{k}={result[k]}' for k in result])
                msg = f'RESULT({msg})'
                break
        except Exception as e:
            emoji = '🔴'
            result = c.detailed_error(e)
            msg = f'Error({result})'
            
        c.print(emoji + msg + emoji, 
                color='cyan', 
                verbose=True)
        
        return result


    def cancel_futures(self):
        for f in self.futures:
            f.cancel()

    epoch2results = {}

    @classmethod
    def run_epoch(cls, network='local', vali=None, run_loop=False, update=1, **kwargs):
        if vali != None:
            cls = c.module(vali)
        self = cls(network=network, run_loop=run_loop, update=update, **kwargs)
        return self.epoch(df=1)

    def epoch(self, df=True):
        """
        The following runs an epoch for the validator
        
        """
        if self.epochs > 0:
            self.sync_network()
        self.epochs += 1
        module_addresses = c.shuffle(list(self.namespace.values()))
        c.print(f'Epoch {self.epochs} with {self.n} modules', color='yellow')
        batch_size = min(self.config.batch_size, len(module_addresses)//4)            
        results = []
        for module_address in module_addresses:
            if not self.executor.is_full:
                self.futures.append(self.executor.submit(self.eval, [module_address], timeout=self.config.timeout))
            if len(self.futures) >= batch_size:
                results.append(self.get_next_result(self.futures))
        while len(self.futures) > 0:
            results.append(self.get_next_result())
        results = [r for r in results if r.get('w', 0) > 0]
        if df:
            if len(results) > 0 and 'w' in results[0]:

                results =  c.df(results)
                results = results.sort_values(by='w', ascending=False)
     
        return results

    @property
    def network_staleness(self) -> int:
        """
        The staleness of the network
        """
        return c.time() - self.last_sync_time

    def filter_module(self, module:str, search=None):
        search = search or self.config.search
        if ',' in str(search):
            search_list = search.split(',')
        else:
            search_list = [search]
        return all([s == None or s in module  for s in search_list ])

    def sync_network(self,  
                     network:str=None, 
                      netuid:int=None,
                      search = None, 
                      max_network_staleness=None):
        self.init_state()
        config = self.config
        network = network or config.network
        netuid =  netuid or config.netuid
        search = search or config.search
        max_network_staleness = max_network_staleness or config.max_network_staleness
        if self.network_staleness < max_network_staleness:
            return {'msg': 'Alredy Synced network Within Interval', 
                    'staleness': self.network_staleness, 
                    'max_network_staleness': self.config.max_network_staleness,
                    'network': network, 
                    'netuid': netuid, 
                    'n': self.n,
                    'search': search,
                    }
        self.last_sync_time = c.time()
        # RESOLVE THE VOTING NETWORKS
        if 'local' in network:
            # local network does not need to be updated as it is atomically updated
            namespace = c.get_namespace(search=search, update=1, max_age=max_network_staleness)
        elif 'subspace' in network:
            # the network is a voting network
            self.subspace = c.module('subspace')(network=network, netuid=netuid)
            namespace = self.subspace.namespace(netuid=netuid, update=1)
        namespace = {k: v for k, v in namespace.items() if self.filter_module(k)}
        self.namespace = namespace
        self.n  = len(self.namespace)    
        config.network = network
        config.netuid = netuid
        self.config = config
        c.print(f'Network(network={config.network}, netuid={config.netuid} n=self.n)')
        self.network_state = {
            'network': network,
            'netuid': netuid,
            'n': self.n,
            'search': search,
            'namespace': namespace,
            
        }

        self.put_json(self.path + '/network', self.network_state)

        return 
    

    
    def next_module(self):
        return c.choice(list(self.namespace.keys()))

    module2last_update = {}
    
    def check_info(self, info:dict) -> bool:
        return bool(isinstance(info, dict) and all([k in info for k in  ['w', 'address', 'name', 'key']]))

    def eval(self,  module:str, **kwargs):
        """
        The following evaluates a module sver
        """
        alpha = self.config.alpha
        try:
            info = {}
            # RESOLVE THE NAME OF THE ADDRESS IF IT IS NOT A NAME
            path = self.resolve_path(self.path +'/'+ module)
            address = self.namespace.get(module, module)
            module_client = c.connect(address, key=self.key)
            info = self.get_json(path, {})
            last_timestamp = info.get('timestamp', 0)
            info['staleness'] = c.time() -  last_timestamp
            if info['staleness'] < self.config.max_staleness:
                raise Exception({'module': info['name'], 
                    'msg': 'Too New', 
                    'staleness': info['staleness'], 
                    'max_staleness': self.config.max_staleness,
                    'timeleft': self.config.max_staleness - info['staleness'], 
                    })
            # is the info valid
            if not self.check_info(info):
                info = module_client.info(timeout=self.config.timeout_info)
            self.last_sent = c.time()
            self.requests += 1
            info['timestamp'] = c.timestamp() # the timestamp
            previous_w = info.get('w', 0)

            response = self.score(module_client, **kwargs)
            # PROCESS THE SCORE
            if type(response) in [int, float, bool]:
                # if the response is a number, we want to convert it to a dict
                response = {'w': response}
            response['w'] = float(response.get('w', 0))
            info.update(response)
            info['latency'] = c.round(c.time() - info['timestamp'], 3)
            info['w'] = info['w']  * alpha + previous_w * (1 - alpha)
            #  have a minimum weight to save storage of stale modules
            self.successes += 1
            self.last_success = c.time()
            info['staleness'] = c.round(c.time() - info.get('timestamp', 0), 3)

            if response['w'] > self.config.min_leaderboard_weight:
                self.put_json(path, info)
                
        except Exception as e:
            raise e
            response = c.detailed_error(e)
            response['w'] = 0
            response['name'] = info.get('name', module)
            self.state['errors'] += 1
            self.last_error  = c.time() # the last time an error occured
            info.update(response)
        info.pop('history', None)
        return info
    
    eval_module = eval
      
    @property
    def path(self):
        # the set storage path in config.path is set, then the modules are saved in that directory
        default_path = f'{self.config.network}.{self.config.netuid}' if self.is_voting_network else self.config.network
        self.config.path = self.resolve_path(self.config.get('path', default_path))
        return self.config.path

    def vote_info(self):
        try:
            if not self.is_voting_network:
                return {'success': False, 
                        'msg': 'Not a voting network' , 
                        'network': self.config.network , 
                        'voting_networks': self.voting_networks}
            votes = self.votes()
        except Exception as e:
            votes = {'uids': [], 'weights': []}
            c.print(c.detailed_error(e))
        return {
            'num_uids': len(votes.get('uids', [])),
            'staleness': self.vote_staleness,
            'key': self.key.ss58_address,
            'network': self.config.network,
        }
    
    def votes(self, **kwargs):
        leaderboard =  self.leaderboard(keys=['name', 'w', 'staleness','latency', 'key'],   to_dict=True)
        votes = {'modules': [], 'weights': []}
        for module in self.leaderboard().to_records():
            if module['w'] > 0:
                votes['modules'] += [module['key']]
                votes['weights'] += [module['w']]
        return votes



    
    @property
    def votes_path(self):
        return self.path + f'/votes'

    def vote(self,**kwargs):
        votes =self.votes() 
        return self.subspace.set_weights(modules=votes['modules'], # passing names as uids, to avoid slot conflicts
                            weights=votes['weights'], 
                            key=self.key, 
                            network=self.config.network, 
                            netuid=self.config.netuid,
                            )
    
    set_weights = vote 

    def module_info(self, **kwargs):
        if hasattr(self, 'subspace'):
            return self.subspace.module_info(self.key.ss58_address, netuid=self.config.netuid, **kwargs)
        else:
            return {}
    
    def leaderboard(self,
                    keys = ['name', 'w',  'staleness', 'latency',  'address', 'staleness', 'key'],
                    max_age = None,
                    ascending = True,
                    by = 'w',
                    to_dict = False,
                    n = None,
                    page = None,
                    **kwargs
                    ):
        max_age = max_age or self.config.epoch_time
        paths = self.paths()
        df = []
        # chunk the jobs into batches
        for path in paths:
            r = self.get(path, {},  max_age=max_age)
            if isinstance(r, dict) and 'key' and  r.get('w', 0) > self.config.min_leaderboard_weight  :
                r['staleness'] = c.time() - r.get('timestamp', 0)
                if not self.filter_module(r.get('name', None)):
                    continue
                df += [{k: r.get(k, None) for k in keys}]
            else :
                # removing the path as it is not a valid module and is too old
                self.rm(path)

        df = c.df(df) 
        
        if len(df) == 0:
            return c.df(df)
        if isinstance(by, str):
            by = [by]
        df = df.sort_values(by=by, ascending=ascending)
        if n != None:
            if page != None:
                df = df[page*n:(page+1)*n]
            else:
                df = df[:n]

        # if to_dict is true, we return the dataframe as a list of dictionaries
        if to_dict:
            return df.to_dict(orient='records')

        return df

    def paths(self):
        paths = self.ls(self.path)
        return paths
    
    def refresh_leaderboard(self):
        path = self.path
        r = self.rm(path)
        df = self.leaderboard()
        assert len(df) == 0, f'Leaderboard not removed {df}'
        return {'success': True, 'msg': 'Leaderboard removed', 'path': path}
    
    refresh = refresh_leaderboard 
    
    def save_module_info(self, k:str, v:dict,):
        path = self.path + f'/{k}'
        self.put(path, v)

    @property
    def vote_staleness(self):
        try:
            if 'subspace' in self.config.network:
                return self.subspace.block - self.module_info()['last_update']
        except Exception as e:
            pass
        return 0
    
        
    @staticmethod
    def test( 
            n=2, 
                sleep_time=8, 
                timeout = 20,
                tag = 'vali_test_net',
                miner='module', 
                vali='vali', 
                storage_path = '/tmp/commune/vali_test',
                network='local'):
        
        test_miners = [f'{miner}::{tag}_{i}' for i in range(n)]
        test_vali = f'{vali}::{tag}'
        modules = test_miners + [test_vali]
        for m in modules:
            c.kill(m) 
        for m in modules:
            c.print(c.serve(m, kwargs={'network': network, 
                                        'storage_path': storage_path,
                                        'search': test_miners[0][:-1]}))
        t0 = c.time()
        while not c.server_exists(test_vali):
            time_elapsed = c.time() - t0
            if time_elapsed > timeout:
                return {'success': False, 'msg': 'subnet test failed'}
            c.sleep(1)
            c.print(f'Waiting for {test_vali} to get the Leaderboard {time_elapsed}/{timeout} seconds')

        t0 = c.time()
        c.print(f'Sleeping for {sleep_time} seconds')
        c.print(c.call(test_vali+'/refresh_leaderboard'))
        leaderboard = None
        while c.time() - t0 < sleep_time:
            try:
                vali = c.connect(test_vali)
                leaderboard = c.call(test_vali+'/leaderboard')
                c.print(f'Waiting for leaderboard to be updated {len(leaderboard)} is n={n}')
                if len(leaderboard) >= n:
                    break
                c.sleep(1)
            except Exception as e:
                print(e)

        leaderboard = c.call(test_vali+'/leaderboard', df=1)
        assert isinstance(leaderboard, pd.DataFrame), leaderboard
        assert len(leaderboard) >= n, leaderboard
        c.print(c.call(test_vali+'/refresh_leaderboard'))        
        for miner in test_miners + [test_vali]:
            c.print(c.kill(miner))
        return {'success': True, 'msg': 'subnet test passed'}

if __name__ == '__main__':
    Vali.run()