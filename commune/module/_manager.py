
from typing import *
import os
from copy import deepcopy

class Manager:
    avoid_dirnames = ['', 'src', 'commune', 'commune/module', 'commune/modules', 'modules', 'blocks', 'agents', 'commune/agents']
    extension = '.py'
    @classmethod
    def resolve_extension(cls, filename:str, extension = '.py') -> str:
        if filename.endswith(extension):
             return filename
        return filename + extension

    @classmethod
    def simple2path(cls, 
                    simple:str,
                    extension = extension,
                    avoid_dirnames = avoid_dirnames,
                    **kwargs) -> bool:
        """
        converts the module path to a file path

        for example 

        model.openai.gpt3 -> model/openai/gpt3.py, model/openai/gpt3_module.py, model/openai/__init__.py 
        model.openai -> model/openai.py or model/openai_module.py or model/__init__.py

        Parameters:
            path (str): The module path
        """
        # if cls.libname in simple and '/' not in simple and cls.can_import_module(simple):
        #     return simple
        shortcuts = cls.shortcuts()
        simple = shortcuts.get(simple, simple)


        if simple.endswith(extension):
            simple = simple[:-len(extension)]

        path = None
        pwd = cls.pwd()
        path_options = []
        simple = simple.replace('/', '.')

        dir_paths = list([pwd+ '/' + x for x in avoid_dirnames]) # local first
        dir_paths += list([cls.libpath + '/' + x for x in avoid_dirnames]) # add libpath stuff

        for dir_path in dir_paths:
            # '/' count how many times the path has been split
            module_dirpath = dir_path + '/' + simple.replace('.', '/')
            if os.path.isdir(module_dirpath):
                simple_filename = simple.replace('.', '_')
                filename_options = [simple_filename, simple_filename + '_module', 'module_'+ simple_filename] + ['module'] + simple.split('.') + ['__init__']
                path_options +=  [module_dirpath + '/' + cls.resolve_extension(f)  for f in filename_options]  
            else:
                module_filepath = dir_path + '/' + cls.resolve_extension(simple.replace('.', '/'), extension=extension)
                path_options += [module_filepath]

            for p in path_options:
                if os.path.exists(p):
                    p_text = cls.get_text(p)
                    # gas class in text
                    is_class_text = 'commune' in p_text and 'class ' in p_text or '  def ' in p_text
                    if is_class_text:
                        path = p
                        break
                    path =  p
    
            if path != None:
                break


        assert path != None, f'MODULE {simple} DOES NOT EXIST'
        return path

    
    @classmethod
    def is_repo(cls, libpath:str ):
        # has the .git folder
        return bool([f for f in cls.ls(libpath) if '.git' in f and os.path.isdir(f)])

    
    @classmethod
    def path2simple(cls,  
                    path:str, 
                    tree = None,  
                    ignore_prefixes = ['src', 'commune', 'modules', 'commune.modules',
                                       'commune.commune',
                                        'commune.module', 'module', 'router'],
                    module_folder_filnames = ['__init__', 'main', 'module'],
                    module_extension = 'py',
                    ignore_suffixes = ['module'],
                    name_map = {'commune': 'module'},
                    compress_path = True,
                    verbose = False,
                    num_lines_to_read = 100,
                    ) -> str:
        
        path  = os.path.abspath(path)
        path_filename_with_extension = path.split('/')[-1] # get the filename with extension     
        path_extension = path_filename_with_extension.split('.')[-1] # get the extension
        assert path_extension == module_extension, f'Invalid extension {path_extension} for path {path}'
        path_filename = path_filename_with_extension[:-len(path_extension)-1] # remove the extension
        path_filename_chunks = path_filename.split('_')
        path_chunks = path.split('/')

        if path.startswith(cls.libpath):
            path = path[len(cls.libpath):]
        else:
            # if the tree path is not in the path, we want to remove the root path
            pwd = cls.pwd()
            path = path[len(pwd):] 
        dir_chunks = path.split('/')[:-1] if '/' in path else []
        is_module_folder = all([bool(chunk in dir_chunks) for chunk in path_filename_chunks])
        is_module_folder = is_module_folder or (path_filename in module_folder_filnames)
        if is_module_folder:
            path = '/'.join(path.split('/')[:-1])
        path = path[1:] if path.startswith('/') else path
        path = path.replace('/', '.')
        module_extension = '.'+module_extension
        if path.endswith(module_extension):
            path = path[:-len(module_extension)]

        if compress_path:
            # we want to remove redundant chunks 
            # for example if the path is 'module/module' we want to remove the redundant module
            path_chunks = path.split('.')
            simple_path = []
            for chunk in path_chunks:
                if chunk not in simple_path:
                    simple_path += [chunk]
            simple_path = '.'.join(simple_path)
        else:
            simple_path = path
        # FILTER PREFIXES  
        for prefix in ignore_prefixes:
            prefix += '.'
            if simple_path.startswith(prefix) and simple_path != prefix:
                simple_path = simple_path[len(prefix):]
                cls.print(f'Prefix {prefix} in path {simple_path}', color='yellow', verbose=verbose)
        # FILTER SUFFIXES
        for suffix in ignore_suffixes:
            suffix = '.' + suffix
            if simple_path.endswith(suffix) and simple_path != suffix:
                simple_path = simple_path[:-len(suffix)]
                cls.print(f'Suffix {suffix} in path {simple_path}', color='yellow', verbose=verbose)

        # remove leading and trailing dots
        if simple_path.startswith('.'):
            simple_path = simple_path[1:]
        if simple_path.endswith('.'):
            simple_path = simple_path[:-1]
        simple_path = name_map.get(simple_path, simple_path)
        return simple_path

    @classmethod
    def path_config_exists(cls, path:str,
                            config_files = ['config.yaml', 'config.yml'],
                              config_extensions=['.yaml', '.yml']) -> bool:
        '''
        Checks if the path exists
        '''
        config_files += [path.replace('.py', ext) for ext in config_extensions]
        dirpath = os.path.dirname(path)
        dir_files =  os.listdir(dirpath)
        if os.path.exists(dirpath) and any([[f.endswith(cf) for cf in config_files] for f in dir_files]):
            return True
        return False


    @classmethod
    def resolve_cache_path(self, path):
        path = path.replace("/", "_")
        if path.startswith('_'):
            path = path[1:]
        path = f'cached_path/{path}'
        print(path)
        return path
    
    @classmethod
    def cached_paths(cls):
        return cls.ls('cached_paths')
    

    @classmethod
    def find_classes(cls, path='./',  working=False):

        path = os.path.abspath(path)
        if os.path.isdir(path):
            classes = []
            for p in cls.glob(path+'/**/**.py', recursive=True):
                if p.endswith('.py'):
                    p_classes =  cls.find_classes(p )
                    if working:
                        for class_path in p_classes:
                            try:
                                cls.import_object(class_path)
                                classes += [class_path]
                            except Exception as e:
                                r = cls.detailed_error(e)
                                r['class'] = class_path
                                cls.print(r, color='red')
                                continue
                    else:
                        classes += p_classes
                        
            return classes
        
        code = cls.get_text(path)
        classes = []
        file_path = cls.path2objectpath(path)
            
        for line in code.split('\n'):
            if all([s in line for s in ['class ', ':']]):
                new_class = line.split('class ')[-1].split('(')[0].strip()
                if new_class.endswith(':'):
                    new_class = new_class[:-1]
                if ' ' in new_class:
                    continue
                classes += [new_class]
        classes = [file_path + '.' + c for c in classes]

        libpath_objpath_prefix = cls.libpath.replace('/', '.')[1:] + '.'
        classes = [c.replace(libpath_objpath_prefix, '') for c in classes]
        return classes
    
    @classmethod
    def path2objectpath(cls, path:str, pwd=None, **kwargs) -> str:
        pwd = pwd or cls.pwd()
        return path.replace(pwd, '')[1:].replace('/', '.').replace('.py', '')
    @classmethod
    def find_functions(cls, path, working=True):
        fns = []
        if os.path.isdir(path):
            path = os.path.abspath(path)
            for p in cls.glob(path+'/**/**.py', recursive=True):
                p_fns = cls.find_functions(p)
                file_object_path = cls.path2objectpath(p)
                p_fns = [file_object_path + '.' + f for f in p_fns]
                if working:
                    for fn in p_fns:
                        try:
                            cls.import_object(fn)
                        except Exception as e:
                            r = cls.detailed_error(e)
                            r['fn'] = fn
                            cls.print(r, color='red')
                            continue
                        fns += [fn]

        else:
            code = cls.get_text(path)
            for line in code.split('\n'):
                if line.startswith('def ') or line.startswith('async def '):
                    fn = line.split('def ')[-1].split('(')[0].strip()
                    fns += [fn]
        return fns
    

    @classmethod
    def find_async_functions(cls, path):
        if os.path.isdir(path):
            path2classes = {}
            for p in cls.glob(path+'/**/**.py', recursive=True):
                path2classes[p] = cls.find_functions(p)
            return path2classes
        code = cls.get_text(path)
        fns = []
        for line in code.split('\n'):
            if line.startswith('async def '):
                fn = line.split('def ')[-1].split('(')[0].strip()
                fns += [fn]
        return [c for c in fns]
    
    @classmethod
    def find_objects(cls, path:str = './', working=False, **kwargs):
        classes = cls.find_classes(path, working=working)
        object_paths = classes
        return object_paths
    

    def find_working_objects(self, path:str = './', **kwargs):
        objects = self.find_objects(path, **kwargs)
        working_objects = []
        progress = self.tqdm(objects, desc='Progress')
        error_progress = self.tqdm(objects, desc='Errors')

        for obj in objects:

            try:
                self.import_object(obj)
                working_objects += [obj]
                progress.update(1)
            except:
                error_progress.update(1)
                pass
        return working_objects

    search = find_objects

    @classmethod
    def simple2objectpath(cls, 
                          simple_path:str,
                           cactch_exception = False, 
                           **kwargs) -> str:

        object_path = cls.simple2path(simple_path, **kwargs)
        classes =  cls.find_classes(object_path)
        return classes[-1]



    @classmethod
    def simple2object(cls, path:str, **kwargs) -> str:
        path =  cls.simple2objectpath(path, **kwargs)
        return cls.import_object(path)


    included_pwd_in_path = False
    @classmethod
    def import_module(cls, 
                      import_path:str, 
                      included_pwd_in_path=True, 
                      try_prefixes = ['commune','commune.modules', 'modules', 'commune.subspace', 'subspace']
                      ) -> 'Object':
        from importlib import import_module
        if included_pwd_in_path and not cls.included_pwd_in_path:
            import sys
            pwd = cls.pwd()
            sys.path.append(pwd)
            sys.path = list(set(sys.path))
            cls.included_pwd_in_path = True

        # if commune is in the path more than once, we want to remove the duplicates
        if cls.libname in import_path:
            import_path = cls.libname + import_path.split(cls.libname)[-1]
        pwd = cls.pwd()
        try:
            return import_module(import_path)
        except Exception as _e:
            for prefix in try_prefixes:
                try:
                    return import_module(f'{prefix}.{import_path}')
                except Exception as e:
                    pass
            raise _e
    
    @classmethod
    def can_import_module(cls, module:str) -> bool:
        '''
        Returns true if the module is valid
        '''
        try:
            cls.import_module(module)
            return True
        except:
            return False
    @classmethod
    def can_import_object(cls, module:str) -> bool:
        '''
        Returns true if the module is valid
        '''
        try:
            cls.import_object(module)
            return True
        except:
            return False

    @classmethod
    def import_object(cls, key:str, verbose: bool = 0, trials=3)-> Any:
        '''
        Import an object from a string with the format of {module_path}.{object}
        Examples: import_object("torch.nn"): imports nn from torch
        '''
        module = '.'.join(key.split('.')[:-1])
        object_name = key.split('.')[-1]
        if verbose:
            cls.print(f'Importing {object_name} from {module}')
        
        obj =  getattr(cls.import_module(module), object_name)
        return obj


    @classmethod
    def object_exists(cls, path:str, verbose=False)-> Any:
        try:
            cls.import_object(path, verbose=verbose)
            return True
        except Exception as e:
            return False
    
    imp = get_object = importobj = import_object

    @classmethod
    def module_exists(cls, module:str, **kwargs) -> bool:
        '''
        Returns true if the module exists
        '''
        module_exists =  module in cls.modules(**kwargs)
        if not module_exists:
            try:
                module_path = cls.simple2path(module)
                module_exists = cls.exists(module_path)
            except:
                pass
        return module_exists
    
    @classmethod
    def has_app(cls, module:str, **kwargs) -> bool:
        return cls.module_exists(module + '.app', **kwargs)
    
    @classmethod
    def objectpath2module_path(cls, p):
        chunks = p.split('.')
        file_name = chunks[-2]
        chunks = chunks[:-1]
        path = ''
        for chunk in chunks:
            if chunk in path:
                continue
            path += chunk + '.'
        if file_name.endswith('_module'):
            path = '.'.join(path.split('.')[:-1])
        
        if path.startswith(cls.libname + '.'):
            path = path[len(cls.libname)+1:]

        if path.endswith('.'):
            path = path[:-1]

        if '_' in file_name:
            file_chunks =  file_name.split('_')
            if all([c in path for c in file_chunks]):
                path = '.'.join(path.split('.')[:-1])

        return path

    @classmethod
    def local_modules(cls, search=None):
        objects = cls.find_classes(cls.pwd())
        object_paths = [cls.objectpath2module_path(obj) for obj in objects]
        if search != None:
            object_paths = [obj for obj in object_paths if search in obj]
        return sorted(list(set(object_paths)))

    @classmethod
    def lib_modules(cls, search=None):
        objects = cls.find_classes(cls.libpath, )
        object_paths = [cls.objectpath2module_path(obj) for obj in objects]
        if search != None:
            object_paths = [obj for obj in object_paths if search in obj]
        return sorted(list(set(object_paths)))
    
    @classmethod
    def find_modules(cls, search=None, **kwargs):
        local_modules = cls.local_modules(search=search)
        lib_modules = cls.lib_modules(search=search)
        return sorted(list(set(local_modules + lib_modules)))

    _modules = None
    @classmethod
    def modules(cls, search=None, cache=True,   **kwargs)-> List[str]:
        modules = cls._modules
        if not cache or modules == None:
            modules =  cls.find_modules(search=None, **kwargs)
        if search != None:
            modules = [m for m in modules if search in m]
        return modules
    get_modules = modules

    @classmethod
    def has_module(cls, module):
        return module in cls.modules()