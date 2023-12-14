import commune as c
Thread = c.module('thread')
import asyncio
import gc
class Router(c.Module):
    default_fn = 'info'
    fn_splitter = '/'

    def __init__(self, max_workers=10):
        self.executor = c.module('executor.thread')(max_workers=max_workers)


    def call(self, server, *args,  fn_splitter='/', return_future=False, **kwargs):
        args = args or []
        kwargs = kwargs or {}
        if fn_splitter in server:
            fn = server.split(fn_splitter)[1]
            server = fn_splitter.join(server.split(fn_splitter)[:1])
        else:
            fn = fn or self.default_fn
        result = self.executor.submit(c.call, args=[server],  kwargs={'fn':fn,  **kwargs}, return_future=return_future)
        return result


    def servers(self, network:str='local'):
        return c.servers(network=network)
    
    def namespace(self, network:str='local'):
        return c.namespace(network=network)



                
        



        


