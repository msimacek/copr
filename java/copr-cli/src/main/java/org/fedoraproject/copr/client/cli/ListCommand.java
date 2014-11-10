package org.fedoraproject.copr.client.cli;

import java.util.ArrayList;
import java.util.List;

import org.fedoraproject.copr.client.CoprException;
import org.fedoraproject.copr.client.CoprSession;
import org.fedoraproject.copr.client.ListRequest;
import org.fedoraproject.copr.client.ListResult;
import org.fedoraproject.copr.client.ProjectId;

import com.beust.jcommander.Parameter;
import com.beust.jcommander.ParameterException;

public class ListCommand
    implements CliCommand
{

    @Parameter( required = true )
    private List<String> names = new ArrayList<>();

    @Override
    public void run( CoprSession session )
        throws CoprException
    {
        if ( names.size() != 1 )
        {
            throw new ParameterException( "Exactly one name argument required" );
        }
        ListRequest request = new ListRequest();
        request.setUserName( names.get( 0 ) );
        ListResult result = session.list( request );
        for ( ProjectId id : result.getProjects() )
        {
            System.out.println( id.getProjectName() );
        }
    }

}
