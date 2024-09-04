

from typing import *
thread_map = {}

def wait(futures:list, timeout:int = None, generator:bool=False, return_dict:bool = True) -> list:
    import commune as c
    is_singleton = bool(not isinstance(futures, list))

    futures = [futures] if is_singleton else futures
    # if type(futures[0]) in [asyncio.Task, asyncio.Future]:
    #     return gather(futures, timeout=timeout)
        
    if len(futures) == 0:
        return []
    if is_coroutine(futures[0]):
        return c.gather(futures, timeout=timeout)
    
    future2idx = {future:i for i,future in enumerate(futures)}

    if timeout == None:
        if hasattr(futures[0], 'timeout'):
            timeout = futures[0].timeout
        else:
            timeout = 30

    if generator:
        def get_results(futures):
            import concurrent 
            try: 
                for future in concurrent.futures.as_completed(futures, timeout=timeout):
                    if return_dict:
                        idx = future2idx[future]
                        yield {'idx': idx, 'result': future.result()}
                    else:
                        yield future.result()
            except Exception as e:
                yield None
            
    else:
        def get_results(futures):
            import concurrent
            results = [None]*len(futures)
            try:
                for future in concurrent.futures.as_completed(futures, timeout=timeout):
                    idx = future2idx[future]
                    results[idx] = future.result()
                    del future2idx[future]
                if is_singleton: 
                    results = results[0]
            except Exception as e:
                unfinished_futures = [future for future in futures if future in future2idx]
                print(f'Error: {e}, {len(unfinished_futures)} unfinished futures with timeout {timeout} seconds')
            return results

    return get_results(futures)


def submit(
            fn, 
            params = None,
            kwargs: dict = None, 
            args:list = None, 
            timeout:int = 40, 
            return_future:bool=True,
            init_args : list = [],
            init_kwargs:dict= {},
            executor = None,
            module: str = None,
            mode:str='thread',
            max_workers : int = 100,
            ):
    import commune as c
    kwargs = {} if kwargs == None else kwargs
    args = [] if args == None else args
    if params != None:
        if isinstance(params, dict):
            kwargs = {**kwargs, **params}
        elif isinstance(params, list):
            args = [*args, *params]
        else:
            raise ValueError('params must be a list or a dictionary')
    
    fn = c.get_fn(fn)
    executor = c.module('executor')(max_workers=max_workers, mode=mode) if executor == None else executor
    args = c.copy(args)
    kwargs = c.copy(kwargs)
    init_kwargs = c.copy(init_kwargs)
    init_args = c.copy(init_args)
    if module == None:
        module = c.get_module('module')
    else:
        module = module(module)
    if isinstance(fn, str):
        method_type = c.classify_fn(getattr(module, fn))
    elif callable(fn):
        method_type = c.classify_fn(fn)
    else:
        raise ValueError('fn must be a string or a callable')
    
    if method_type == 'self':
        module = module(*init_args, **init_kwargs)

    future = executor.submit(fn=fn, args=args, kwargs=kwargs, timeout=timeout)
        
    if return_future:
        return future
    else:
        return wait(future, timeout=timeout)




def as_completed(futures:list, timeout:int=10, **kwargs):
    import concurrent
    return concurrent.futures.as_completed(futures, timeout=timeout)


def is_coroutine(future):
    import commune as c
    """
    returns True if future is a coroutine
    """
    return c.obj2typestr(future) == 'coroutine'




def thread(fn: Union['callable', str],  
                args:list = None, 
                kwargs:dict = None, 
                daemon:bool = True, 
                name = None,
                tag = None,
                start:bool = True,
                tag_seperator:str='::', 
                **extra_kwargs):
    import threading
    import commune as c
    
    if isinstance(fn, str):
        fn = c.get_fn(fn)
    if args == None:
        args = []
    if kwargs == None:
        kwargs = {}

    assert callable(fn), f'target must be callable, got {fn}'
    assert  isinstance(args, list), f'args must be a list, got {args}'
    assert  isinstance(kwargs, dict), f'kwargs must be a dict, got {kwargs}'
    
    # unique thread name
    if name == None:
        name = fn.__name__
        cnt = 0
        while name in thread_map:
            cnt += 1
            if tag == None:
                tag = ''
            name = name + tag_seperator + tag + str(cnt)
    
    if name in thread_map:
        thread_map[name].join()

    t = threading.Thread(target=fn, args=args, kwargs=kwargs, **extra_kwargs)
    # set the time it starts
    setattr(t, 'start_time', c.time())
    t.daemon = daemon
    if start:
        t.start()
    thread_map[name] = t
    return t


def threads(search:str = None):
    threads =  list(thread_map.keys())
    if search != None:
        threads = [t for t in threads if search in t]
    return threads
